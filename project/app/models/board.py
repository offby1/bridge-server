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

    from app.models import Player

BOARDS_PER_TOURNAMENT = 16

logger = logging.getLogger(__name__)


def get_rng_from_seeds(*seed_args: bytes) -> random.Random:
    rv = random.Random()
    h = hashlib.sha256()
    for arg in seed_args:
        h.update(arg)

    rv.seed(int.from_bytes(h.digest()))
    return rv


def board_attributes_from_display_number(
    *,
    display_number: int,
    rng_seeds: list[bytes],
) -> dict[str, Any]:
    assert (
        1 <= display_number <= BOARDS_PER_TOURNAMENT
    ), f"{display_number=} gotta be <= {BOARDS_PER_TOURNAMENT=}"

    # https://en.wikipedia.org/wiki/Board_(bridge)#Set_of_boards
    dealer = "NESW"[(display_number - 1) % 4]
    only_ns_vuln = display_number in (2, 5, 12, 15)
    only_ew_vuln = display_number in (3, 6, 9, 16)
    all_vuln = display_number in (4, 7, 10, 13)

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
        "display_number": display_number,
        "north_cards": north_cards,
        "east_cards": east_cards,
        "south_cards": south_cards,
        "west_cards": west_cards,
    }


class TournamentManager(models.Manager):
    # When should we call this?
    # Whenever there are no more unplayed boards.
    def create(self, *args, **kwargs) -> Tournament:
        with transaction.atomic():
            t = super().create(*args, **kwargs)
            # create all the boards ahead of time.
            for display_number in range(1, BOARDS_PER_TOURNAMENT + 1):
                board_attributes = board_attributes_from_display_number(
                    display_number=display_number,
                    rng_seeds=[
                        str(display_number).encode(),
                        str(t.pk).encode(),
                        settings.SECRET_KEY.encode(),
                    ],
                )
                Board.objects.create_from_attributes(attributes=board_attributes, tournament=t)
            logger.debug("Created new tournament with %s", t.board_set.all())
            return t

    def maybe_new_tournament(self) -> Tournament | None:
        with transaction.atomic():
            currently_running = self.filter(is_complete=False).first()
            if currently_running is not None:
                currently_running.maybe_complete()
                logger.debug("An incomplete tournament already exists; no need to create a new one")
                return None
            rv = self.create()
            logger.debug("No incomplete tournaments exist; here's a new one: %s", rv)
            return rv


# This might actually be a "session" as per https://en.wikipedia.org/wiki/Duplicate_bridge#Pairs_game
class Tournament(models.Model):
    objects = TournamentManager()

    is_complete = models.BooleanField(default=False)

    def __str__(self) -> str:
        return f"tournament {self.pk}"

    def maybe_complete(self) -> None:
        from app.models import Hand

        logger.debug("If only there were some way that I, %s, could tell if I were complete", self)
        boards = self.board_set.all()
        logger.debug("I dunno, maybe I should check all my boards: %s", boards)
        hands = Hand.objects.filter(board__in=boards)
        logger.debug("Or maybe my hands: %s", hands)
        tables = hands.values_list("table", flat=True).all()
        logger.debug("Or maybe my tables: %s", tables)
        players = boards.values_list("player", flat=True).all()
        logger.debug("Or maybe my players: %s", players)

    def _check_no_more_than_one_running_tournament(self):
        if self.is_complete:
            return

        if Tournament.objects.filter(is_complete=False).exists():
            msg = "Cannot save incomplete tournament %s when you've already got one going, Mrs Mulwray"
            raise Exception(msg, self)

    def save(self, *args, **kwargs):
        self._check_no_more_than_one_running_tournament()
        super().save(*args, **kwargs)


class BoardManager(models.Manager):
    def nicely_ordered(self) -> models.QuerySet:
        return self.order_by("tournament", "display_number")

    def create_from_attributes(self, *, attributes, tournament) -> Board:
        return self.create(**attributes, tournament=tournament)


class Board(models.Model):
    class PlayerVisibility(enum.Enum):
        nothing = enum.auto()
        own_hand = enum.auto()
        dummys_hand = enum.auto()
        everything = enum.auto()

    if TYPE_CHECKING:
        hand_set = RelatedManager[Hand]()

    display_number = models.SmallIntegerField()

    ns_vulnerable = models.BooleanField()
    ew_vulnerable = models.BooleanField()

    dealer = models.CharField(db_comment="""corresponds to bridge library's "direction" """)  # type: ignore

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
    def hand_strings_by_direction(self) -> dict[str, str]:
        return {
            Seat.NORTH.value: self.north_cards,
            Seat.EAST.value: self.east_cards,
            Seat.SOUTH.value: self.south_cards,
            Seat.WEST.value: self.west_cards,
        }

    def cards_for_direction(self, direction_letter: str) -> list[Card]:
        card_string = self.hand_strings_by_direction[direction_letter]
        return [Card.deserialize("".join(c)) for c in more_itertools.chunked(card_string, 2)]

    def what_can_they_see(self, *, player: Player) -> PlayerVisibility:
        hand = player.hand_at_which_board_was_played(self)
        if hand is None:
            return self.PlayerVisibility.nothing

        rv = self.PlayerVisibility.own_hand

        if next(hand.get_xscript().plays(), None) is not None:
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

    def short_string(self) -> str:
        return f"Board #{self.display_number} ({self.tournament})"

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

    class Meta:
        constraints = [
            models.CheckConstraint(  # type: ignore[call-arg]
                name="%(app_label)s_%(class)s_dealer_must_be_compass_letter",
                condition=models.Q(dealer__in="NESW"),
            ),
        ]


admin.site.register(Board)
