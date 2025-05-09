from __future__ import annotations

import enum
import functools
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
from django.db import models

from .common import SEAT_CHOICES

if TYPE_CHECKING:
    from django.db.models.manager import RelatedManager

    from app.models import Player, Tournament

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
    disp_mod_16 = display_number % 16
    dealer = "NESW"[(disp_mod_16 - 1) % 4]
    only_ns_vuln = disp_mod_16 in (2, 5, 12, 15)
    only_ew_vuln = disp_mod_16 in (3, 6, 9, 16)
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

# fmt:off

# fmt:on
class Board(models.Model):
    @functools.total_ordering
    class PlayerVisibility(enum.Enum):
        nothing = enum.auto()
        own_hand = enum.auto()
        dummys_hand = enum.auto()
        everything = enum.auto()

        def __lt__(self, other) -> bool:
            return self.value < other.value

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

    from app.models.tournament import Tournament

    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE)
    group = models.CharField(
        max_length=1,
        null=True,
        db_comment=""" A, B, C &c, NULL means not yet assigned """,  # type: ignore [call-overload]
    )

    objects = BoardManager()

    def was_played_at_table(self, *, table_display_number: int) -> models.QuerySet:
        qs = self.hand_set.filter(table_display_number=table_display_number)
        return qs

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

    # Who can see which cards (and when)?

    # a "None" player means the anonymous user.
    # cases to check:
    # (no need to check, just a reminder): if the tournament is still in signup mode, there *are* no boards
    # - if the tournament is complete, everyone can see everything.
    # - otherwise the tournament is running, and ...
    #   - if player is None, they can see nothing, since otherwise a player could get a new browser window, peek at the hand they're currently playing, and cheat up the yin-yang
    #   - if it's a Player, and they are not signed up for this tournament: they can see nothing, since again it'd be too easy to cheat (just sign up a new username)
    #   - if it's a Player, and they are in this tournament:
    #     - if they have not yet played this board, nope
    #     - if they have been seated at a hand with this board:
    #       - if it's their own cards, of course they can see them
    #       - if the opening lead has been played, they can also see the dummy
    #       - if the hand is complete (either passed out, or all 13 tricks played), they can also see their opponent's cards (i.e., everything)

    def can_see_cards_at(self, *, player: Player | None, direction_letter: str) -> bool:
        # logger.error(f"{self.what_can_they_see(player=player)=}")
        match self.what_can_they_see(player=player):
            case self.PlayerVisibility.everything:
                return True
            case self.PlayerVisibility.nothing:
                return False
            case self.PlayerVisibility.own_hand:
                assert player is not None
                hand = player.hand_at_which_we_played_board(self)
                assert hand is not None

                # logger.debug(f"{player.name=} == {hand.players_by_direction_letter[direction_letter]=} ? ...")
                return player == hand.players_by_direction_letter[direction_letter]
            case self.PlayerVisibility.dummys_hand:
                assert player is not None
                hand = player.hand_at_which_we_played_board(self)
                assert hand is not None

                # logger.debug(f"{player.name=} == {hand.players_by_direction_letter[direction_letter].name=} ? ...")
                if player == hand.players_by_direction_letter[direction_letter]:
                    return True

                # lt = hand.players_by_direction_letter[direction_letter].libraryThing()
                # logger.debug(f"{lt=} ...")
                # dummy = hand.dummy
                # logger.debug(f"{dummy=}...")

                return (
                    hand.get_xscript().num_plays > 0
                    and hand.players_by_direction_letter[direction_letter].libraryThing()
                    == hand.dummy
                )
            case _:
                assert False, f"Dunno what case {self.what_can_they_see(player)=} is"

    def what_can_they_see(self, *, player: Player | None) -> PlayerVisibility:
        if self.tournament.is_complete:
            # logger.error(f"{self.tournament.is_complete=} => {self.PlayerVisibility.everything=}")
            return self.PlayerVisibility.everything

        if player is None:
            # logger.error(f"{player=} is None => {self.PlayerVisibility.nothing=}")
            return self.PlayerVisibility.nothing

        if self.tournament.signup_deadline_has_passed() and player not in self.tournament.players():
            player_name = getattr(player, "name", "?")
            logger.error(
                f"t#{self.tournament.display_number}'s signup deadline has passed; and {player_name=} isn't in that tournament, so => {self.PlayerVisibility.everything=}"
            )
            return self.PlayerVisibility.everything

        hand = player.hand_at_which_we_played_board(self)
        if hand is None:
            # logger.error(f"{hand=} is None => {self.PlayerVisibility.nothing=}")
            return self.PlayerVisibility.nothing

        rv = self.PlayerVisibility.own_hand
        # logger.error(f"{hand=} is not None, so at least {self.PlayerVisibility.own_hand=}")

        if hand.get_xscript().num_plays > 0:
            # logger.error(f"{hand.get_xscript().num_plays=} > 0, so at least {self.PlayerVisibility.dummys_hand=}")
            rv = self.PlayerVisibility.dummys_hand

        if hand.is_complete:
            # logger.error(f"{hand.is_complete=}, so {self.PlayerVisibility.everything=}")
            rv = self.PlayerVisibility.everything

        return rv

    def short_string(self) -> str:
        return (
            f"Board #{self.display_number} t#{self.tournament.display_number}, group {self.group}"
        )

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


# fmt:off




# fmt:on


admin.site.register(Board)
