from __future__ import annotations

import hashlib
import logging
import random
from typing import TYPE_CHECKING, Any

import more_itertools

# A "board" is a little tray with four slots, labeled "North", "East", "West", and "South".  The labels might be red,
# indicating that that pair is vulnerable; or not.  https://en.wikipedia.org/wiki/Board_(bridge) One of the four slots
# says "dealer" next to it.  In each slot are -- you guessed it -- 13 cards.  The board is thus a pre-dealt hand.
from django.conf import settings
from django.contrib import admin
from django.db import models

from bridge.card import Card
from bridge.seat import Seat

from .common import SEAT_CHOICES

if TYPE_CHECKING:
    from django.db.models.manager import RelatedManager

    from app.models import Tournament

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
    assert display_number > 0, f"{display_number=} should be > 0"

    disp_mod_16 = display_number % 16
    dealer = "NESW"[(disp_mod_16 - 1) % 4]
    only_ns_vuln = disp_mod_16 in (2, 5, 12, 15)
    only_ew_vuln = disp_mod_16 in (0, 3, 6, 9)
    all_vuln = disp_mod_16 in (4, 7, 10, 13)

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


class BoardManager(models.Manager):
    def nicely_ordered(self) -> models.QuerySet:
        return self.order_by("tournament", "display_number")

    def get_or_create_from_display_number(
        self, *, display_number: int, tournament: Tournament, group: str
    ) -> tuple[Board, bool]:
        assert len(group) == 1
        defaults = board_attributes_from_display_number(
            display_number=display_number,
            rng_seeds=[
                str(display_number).encode(),
                str(tournament.pk).encode(),
                settings.SECRET_KEY.encode(),
            ],
        )

        defaults["group"] = group

        return self.get_or_create(
            defaults=defaults, tournament=tournament, display_number=display_number
        )


class Board(models.Model):
    if TYPE_CHECKING:
        from app.models import Hand

        hand_set = RelatedManager[Hand]()

    display_number = models.SmallIntegerField()

    # TODO vulnerabilities and dealer could be"GeneratedField"s, based on display_number
    ns_vulnerable = models.BooleanField()
    ew_vulnerable = models.BooleanField()
    dealer = models.CharField(db_comment="""corresponds to bridge library's "direction" """)  # type: ignore

    north_cards = models.CharField(max_length=26)
    east_cards = models.CharField(max_length=26)
    south_cards = models.CharField(max_length=26)
    west_cards = models.CharField(max_length=26)

    from app.models.tournament import Tournament

    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE)
    group = models.CharField(
        max_length=1,
        db_comment=""" A, B, C &c """,  # type: ignore [call-overload]
    )

    objects = BoardManager()

    def was_played_at_table(self, *, table_display_number: int) -> models.QuerySet:
        qs = self.hand_set.filter(table_display_number=table_display_number)
        return qs

    def will_be_played_again(self) -> bool:
        if self.tournament.is_complete:
            return False

        # How many *complete* hands include this board?
        num_completed_hands = self.hand_set.filter(board=self, is_complete=True).count()
        # If that number == the number of tables in this tournament, then no
        # otherwise yes
        mvmt = self.tournament.get_movement()
        return num_completed_hands < len(mvmt.table_settings_by_zb_table_number)

    def save(self, *args, **kwargs):
        assert isinstance(self.north_cards, str), f"Those bastards!! {self.north_cards=}"
        assert (
            len(self.north_cards)
            == len(self.south_cards)
            == len(self.east_cards)
            == len(self.west_cards)
            == 26
        ), f"why no cards {vars(self)}"

        return super().save(*args, **kwargs)

    @property
    def fancy_dealer(self):
        return SEAT_CHOICES[self.dealer]

    @property
    def hand_strings_by_direction_letter(self) -> dict[str, str]:
        return {
            Seat.NORTH.value: self.north_cards,
            Seat.EAST.value: self.east_cards,
            Seat.SOUTH.value: self.south_cards,
            Seat.WEST.value: self.west_cards,
        }

    def cards_for_direction_letter(self, direction_letter: str) -> list[Card]:
        assert direction_letter in "NESW"
        return self.cards_for_seat(Seat(direction_letter))

    def cards_for_direction_string(self, direction_str: str) -> list[Card]:
        assert direction_str in [s.name for s in Seat]
        return self.cards_for_seat(Seat(direction_str[0].upper()))

    def cards_for_seat(self, seat: Seat) -> list[Card]:
        card_string = self.hand_strings_by_direction_letter[seat.value]
        return [Card.deserialize("".join(c)) for c in more_itertools.chunked(card_string, 2)]

    # Who may see which of these cards, and when, is decided in app/visibility.py --
    # not here, and not in the views. `can_see_cards_at`, `what_can_they_see` and
    # `relationship_to` used to live at this spot; they are now
    # `app.visibility.may_see_cards`, `card_visibility_level` and
    # `board_relationship`.

    def short_string(self) -> str:
        return f"Tournament#{self.tournament.display_number}, board #{self.display_number}"

    def vulnerability_string(self) -> str:
        if self.ns_vulnerable and self.ew_vulnerable:
            vuln = "Both sides"
        elif not self.ns_vulnerable and not self.ew_vulnerable:
            vuln = "Neither side"
        elif self.ns_vulnerable:
            vuln = "North/South"
        else:
            vuln = "East/West"

        return f"{vuln} vulnerable"

    def __repr__(self) -> str:
        group_string = ""
        if self.group is not None:
            group_string = f"group {self.group}"
        return f"<Board #{self.display_number} {group_string} t#{self.tournament.display_number} pk={self.pk}>"

    def __str__(self) -> str:
        return f"{self.short_string()}, {self.vulnerability_string()}, dealt by {self.fancy_dealer}"

    class Meta:
        constraints = [
            models.CheckConstraint(  # type: ignore[call-arg]
                name="%(app_label)s_%(class)s_dealer_must_be_compass_letter",
                condition=models.Q(dealer__in="NESW"),
            ),
            models.UniqueConstraint(  # type: ignore[call-arg]
                name="%(app_label)s_%(class)s_display_number_unique_per_tournament",
                fields=["display_number", "tournament_id"],
            ),
        ]


admin.site.register(Board)
