from __future__ import annotations

import enum
import hashlib
import logging
import random
from typing import TYPE_CHECKING

import more_itertools
from bridge.card import Card
from bridge.seat import Seat

# A "board" is a little tray with four slots, labeled "North", "East", "West", and "South".  The labels might be red,
# indicating that that pair is vulnerable; or not.  https://en.wikipedia.org/wiki/Board_(bridge) One of the four slots
# says "dealer" next to it.  In each slot are -- you guessed it -- 13 cards.  The board is thus a pre-dealt hand.
from django.conf import settings
from django.contrib import admin
from django.db import models
from django.db.models.aggregates import Max
from django_eventstream import send_event  # type: ignore [import-untyped]

from .common import SEAT_CHOICES

if TYPE_CHECKING:
    from app.models import Hand, Player
    from django.db.models.manager import RelatedManager

BOARDS_PER_TOURNAMENT = 2

logger = logging.getLogger(__name__)


class Tournament(models.Model):
    def __str__(self) -> str:
        return f"tournament {self.pk}"


def get_rng_for_board(*seed_args: int) -> random.Random:
    print(f"get_rng_for_board: {seed_args=}")
    rv = random.Random()
    h = hashlib.sha256()
    for arg in seed_args:
        h.update(arg.to_bytes())
        print(f"Updated with {arg.to_bytes()!r}")
    h.update(settings.SECRET_KEY.encode())
    seed = int.from_bytes(h.digest())
    print(f"Updated with {settings.SECRET_KEY.encode()=}; {seed=}")
    rv.seed(seed)
    return rv


class BoardManager(models.Manager):
    def get_or_create_from_deck(
        self,
        *,
        deck: list[Card],
        shuffle_deck: bool = False,
    ) -> tuple[Board, bool]:
        # Max seems safer than just using "count", since in the unlikely event that we ever delete a board, "count"
        # would return a duplicate value, whereas Max should not.
        max_number = self.aggregate(max_id=Max("id"))["max_id"]
        if max_number is None:
            max_number = 0
        board_number = max_number + 1

        # https://en.wikipedia.org/wiki/Board_(bridge)#Set_of_boards
        dealer = (board_number - 1) % 4 + 1
        only_ns_vuln = board_number in (2, 5, 12, 15)
        only_ew_vuln = board_number in (3, 6, 9, 16)
        all_vuln = board_number in (4, 7, 10, 13)

        return self.get_or_create_with_deck(
            ns_vulnerable=only_ns_vuln or all_vuln,
            ew_vulnerable=only_ew_vuln or all_vuln,
            dealer=dealer,
            deck=deck,
            number=board_number,
            shuffle_deck=shuffle_deck,
        )

    def get_or_create_with_deck(
        self,
        *,
        ns_vulnerable: bool,
        ew_vulnerable: bool,
        dealer: int,
        deck: list[Card],
        number=int,
        shuffle_deck: bool = False,
    ) -> tuple[Board, bool]:
        def deserialize_hand(cards: list[Card]) -> str:
            # sorted only so that they look purty in the Admin site.
            return "".join([c.serialize() for c in sorted(cards)])

        if shuffle_deck:
            rng = get_rng_for_board(number, self.count() // BOARDS_PER_TOURNAMENT)
            rng.shuffle(deck)
            print(f"{deck[13:26]=}")

        north_cards = deserialize_hand(deck[0:13])
        east_cards = deserialize_hand(deck[13:26])
        south_cards = deserialize_hand(deck[26:39])
        west_cards = deserialize_hand(deck[39:52])

        return self.get_or_create(
            defaults={
                "ns_vulnerable": ns_vulnerable,
                "ew_vulnerable": ew_vulnerable,
                "dealer": dealer,
                "north_cards": north_cards,
                "east_cards": east_cards,
                "south_cards": south_cards,
                "west_cards": west_cards,
            },
            number=number,
        )

    def get_or_create(self, *args, **kwargs):
        from app.serializers import BoardSerializer

        kwargs = kwargs.copy()

        kwargs["number"] = kwargs["number"] % BOARDS_PER_TOURNAMENT

        # Which tournament is this board part of?
        if (tournament := kwargs.get("tournament")) is None:
            print(f"{self.count()=}")
            tournament_number = 1 + (self.count() // BOARDS_PER_TOURNAMENT)
            print(f"{tournament_number=}")
            tournament, _ = Tournament.objects.get_or_create(pk=tournament_number)
            kwargs["tournament"] = tournament

        print(f"{kwargs['tournament']=}")

        new_board, created = super().get_or_create(*args, **kwargs)

        # nobody (yet) cares about the creation of a new board, but what the heck.
        # I'm just testing out this scheme of using drf to serialize the data.

        send_event(
            channel="top-sekrit-board-creation-channel",
            event_type="message",
            data={
                "new-board": BoardSerializer(new_board).data,
            },
        )

        return new_board, created


class Board(models.Model):
    class PlayerVisibility(enum.Enum):
        nothing = enum.auto()
        own_hand = enum.auto()
        dummys_hand = enum.auto()
        everything = enum.auto()

    if TYPE_CHECKING:
        hand_set = RelatedManager[Hand]()

    ns_vulnerable = models.BooleanField()
    ew_vulnerable = models.BooleanField()

    dealer = models.SmallIntegerField(db_comment="""corresponds to bridge library's "direction" """)  # type: ignore

    north_cards = models.CharField(max_length=26)
    east_cards = models.CharField(max_length=26)
    south_cards = models.CharField(max_length=26)
    west_cards = models.CharField(max_length=26)

    number = models.SmallIntegerField()
    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE)

    objects = BoardManager()

    @property
    def fancy_dealer(self):
        return SEAT_CHOICES[self.dealer]

    @property
    def hand_strings_by_direction(self) -> dict[int, str]:
        return {
            Seat.NORTH.value: self.north_cards,
            Seat.EAST.value: self.east_cards,
            Seat.SOUTH.value: self.south_cards,
            Seat.WEST.value: self.west_cards,
        }

    def cards_for_direction(self, direction_integer: int) -> list[Card]:
        card_string = self.hand_strings_by_direction[direction_integer]
        return [Card.deserialize("".join(c)) for c in more_itertools.chunked(card_string, 2)]

    def what_can_they_see(self, *, player: Player) -> PlayerVisibility:
        hand = player.hand_at_which_board_was_played(self)
        if hand is None:
            return self.PlayerVisibility.nothing

        rv = self.PlayerVisibility.own_hand

        if hand.plays.count() > 0:
            rv = self.PlayerVisibility.dummys_hand

        if hand.is_complete:
            rv = self.PlayerVisibility.everything

        return rv

    def save(self, *args, **kwargs):
        assert isinstance(self.north_cards, str), f"Those bastards!! {self.north_cards=}"
        assert (
            len(self.north_cards)
            == len(self.south_cards)
            == len(self.east_cards)
            == len(self.west_cards)
            == 26
        ), f"why no cards {vars(self)}"
        assert Board.objects.filter(tournament=self.tournament).count() < BOARDS_PER_TOURNAMENT
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        if self.ns_vulnerable and self.ew_vulnerable:
            vuln = "Both sides"
        elif not self.ns_vulnerable and not self.ew_vulnerable:
            vuln = "Neither side"
        elif self.ns_vulnerable:
            vuln = "North/South"
        else:
            vuln = "East/West"

        return f"Board #{self.number} ({self.tournament}), {vuln} vulnerable, dealt by {self.fancy_dealer}"

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["number", "tournament"],
                name="%(app_label)s_%(class)s_combination_of_board_number_and_tournament_number",
            ),
        ]


admin.site.register(Board)
