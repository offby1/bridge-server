from __future__ import annotations

import enum
import hashlib
import logging
import random
from typing import TYPE_CHECKING, Any

import more_itertools
from bridge.card import Card
from bridge.seat import Seat

# A "board" is a little tray with four slots, labeled "North", "East", "West", and "South".  The labels might be red,
# indicating that that pair is vulnerable; or not.  https://en.wikipedia.org/wiki/Board_(bridge) One of the four slots
# says "dealer" next to it.  In each slot are -- you guessed it -- 13 cards.  The board is thus a pre-dealt hand.
from django.conf import settings
from django.contrib import admin
from django.db import models, transaction

from .common import SEAT_CHOICES

if TYPE_CHECKING:
    from django.db.models.manager import RelatedManager

    from app.models import Hand, Player

BOARDS_PER_TOURNAMENT = 16

logger = logging.getLogger(__name__)


def get_rng_from_seeds(*seed_args: bytes) -> random.Random:
    rv = random.Random()
    h = hashlib.sha256()
    for arg in seed_args:
        h.update(arg)

    rv.seed(int.from_bytes(h.digest()))
    return rv


def board_attributes_from_board_number(
    *,
    board_number: int,
    rng_seeds: list[bytes],
) -> dict[str, Any]:
    assert (
        0 < board_number <= BOARDS_PER_TOURNAMENT
    ), f"{board_number=} gotta be < {BOARDS_PER_TOURNAMENT=}"

    board_number = (board_number - 1) % 16

    dealer = (board_number - 1) % 4 + 1
    only_ns_vuln = board_number in (2, 5, 12, 15)
    only_ew_vuln = board_number in (3, 6, 9, 16)
    all_vuln = board_number in (4, 7, 10, 13)

    def deserialize_hand(cards: list[Card]) -> str:
        # sorted only so that they look purty in the Admin site.
        return "".join([c.serialize() for c in sorted(cards)])

    rng = get_rng_from_seeds(*rng_seeds)
    deck = Card.deck()
    rng.shuffle(deck)

    north_cards = deserialize_hand(deck[0:13])
    east_cards = deserialize_hand(deck[13:26])
    south_cards = deserialize_hand(deck[26:39])
    west_cards = deserialize_hand(deck[39:52])

    return {
        "ns_vulnerable": only_ns_vuln or all_vuln,
        "ew_vulnerable": only_ew_vuln or all_vuln,
        "dealer": dealer,
        "north_cards": north_cards,
        "east_cards": east_cards,
        "south_cards": south_cards,
        "west_cards": west_cards,
    }


class TournamentManager(models.Manager):
    # When should we call this?
    # Whenever there are no more unplayed boards.
    def create(self, *args, **kwargs) -> None:
        with transaction.atomic():
            t = super().create(*args, **kwargs)
            # create all the boards ahead of time.
            for board_number in range(1, BOARDS_PER_TOURNAMENT + 1):
                board_attributes = board_attributes_from_board_number(
                    board_number=board_number,
                    rng_seeds=[
                        str(board_number).encode(),
                        str(t.pk).encode(),
                        settings.SECRET_KEY.encode(),
                    ],
                )
                Board.objects.create_from_attributes(attributes=board_attributes, tournament=t)


class Tournament(models.Model):
    objects = TournamentManager()

    def __str__(self) -> str:
        return f"tournament {self.pk}"


class BoardManager(models.Manager):
    def nicely_ordered(self) -> models.QuerySet:
        return self.order_by("tournament", 1 + (models.F("pk") % BOARDS_PER_TOURNAMENT))

    def create_from_attributes(self, *, attributes, tournament) -> Board:
        # https://en.wikipedia.org/wiki/Board_(bridge)#Set_of_boards

        return self.create(**attributes, tournament=tournament)


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

    @property
    def number(self) -> int:
        return 1 + (self.pk % BOARDS_PER_TOURNAMENT)

    def short_string(self) -> str:
        return f"Board #{self.number} ({self.tournament})"

    def __str__(self) -> str:
        if self.ns_vulnerable and self.ew_vulnerable:
            vuln = "Both sides"
        elif not self.ns_vulnerable and not self.ew_vulnerable:
            vuln = "Neither side"
        elif self.ns_vulnerable:
            vuln = "North/South"
        else:
            vuln = "East/West"

        return f"{self.short_string()}, {vuln} vulnerable, dealt by {self.fancy_dealer}"


admin.site.register(Board)
