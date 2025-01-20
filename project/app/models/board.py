from __future__ import annotations

import enum
import hashlib
import logging
import random
from typing import TYPE_CHECKING, Any

import more_itertools
import tabulate
from bridge.card import Card
from bridge.seat import Seat

# A "board" is a little tray with four slots, labeled "North", "East", "West", and "South".  The labels might be red,
# indicating that that pair is vulnerable; or not.  https://en.wikipedia.org/wiki/Board_(bridge) One of the four slots
# says "dealer" next to it.  In each slot are -- you guessed it -- 13 cards.  The board is thus a pre-dealt hand.
from django.conf import settings
from django.contrib import admin
from django.db import models, transaction
from django_eventstream import send_event  # type: ignore [import-untyped]

from .common import SEAT_CHOICES

if TYPE_CHECKING:
    from django.db.models.manager import RelatedManager

    from app.models import Player

BOARDS_PER_TOURNAMENT = 2

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
            t.dump_tableau()
            return t

    def maybe_new_tournament(self) -> Tournament | None:
        with transaction.atomic():
            currently_running = self.filter(is_complete=False).first()
            if currently_running is not None:
                currently_running.maybe_complete()
                if not currently_running.is_complete:
                    logger.debug(
                        "An incomplete tournament already exists; no need to create a new one"
                    )
                    return None
            return self.create()


# This might actually be a "session" as per https://en.wikipedia.org/wiki/Duplicate_bridge#Pairs_game
class Tournament(models.Model):
    if TYPE_CHECKING:
        board_set = RelatedManager["Board"]()

    objects = TournamentManager()

    is_complete = models.BooleanField(default=False)

    def __str__(self) -> str:
        return f"tournament {self.pk}"

    def hands(self) -> models.QuerySet:
        from app.models import Hand

        return Hand.objects.filter(board__in=self.board_set.all())

    def tables(self) -> models.QuerySet:
        from app.models import Table

        return Table.objects.filter(hand__in=self.hands())

    def table_pks(self):
        return self.hands().values_list("table", flat=True).all()

    def dump_tableau(self) -> None:
        tableau = []
        for b in self.board_set.order_by("display_number").all():
            tableau.append([(b, h.table) for h in b.hand_set.order_by("pk")])
        print(tabulate.tabulate(tableau))

    def maybe_complete(self) -> None:
        with transaction.atomic():
            logger.debug(
                "Checking hands: %s ... they %s all complete, btw",
                self.hands(),
                "are" if all(h.is_complete for h in self.hands()) else "are not",
            )

            all_hands_are_complete = all(h.is_complete for h in self.hands())
            if all_hands_are_complete:
                self.is_complete = True
                self.save()
                self.eject_all_pairs()
                logger.debug(
                    "Marked myself %s as complete, and ejected all pairs from tables", self
                )
                self.dump_tableau()
                return

            logger.debug("%s: Some of my hands are still being played, so I'm not complete", self)

    def eject_all_pairs(self) -> None:
        logger.debug(
            "Since I just completed, I should go around ejecting partnerships from tables."
        )
        with transaction.atomic():
            for t in self.tables():
                for seat in t.seat_set.all():
                    p: Player = seat.player

                    p.currently_seated = False
                    p.save()
                    logger.debug("%s is now in the lobby", p)

                    send_event(
                        channel=p.event_channel_name,
                        event_type="message",
                        data={"Prepare to": "die"},
                    )

                    p.toggle_bot(False)

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
        from app.models import Hand

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
