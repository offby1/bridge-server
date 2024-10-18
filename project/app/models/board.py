from __future__ import annotations

import enum
from typing import TYPE_CHECKING

import more_itertools
from bridge.card import Card
from bridge.seat import Seat
from django.contrib import admin

# A "board" is a little tray with four slots, labeled "North", "East", "West", and "South".  The labels might be red, indicating that that pair is vulnerable; or not.
# https://en.wikipedia.org/wiki/Board_(bridge)
# One of the four slots says "dealer" next to it.
# In each slot are -- you guessed it -- 13 cards.  The board is thus a pre-dealt hand.
from django.db import models
from django_eventstream import send_event  # type: ignore

from .common import SEAT_CHOICES

if TYPE_CHECKING:
    from django.db.models.manager import RelatedManager

    from app.models import Hand, Player

TOTAL_BOARDS = 16


class BoardManager(models.Manager):
    def create_from_deck(self, *, deck: list[Card]) -> Board:
        board_number = self.count() + 1

        # https://en.wikipedia.org/wiki/Board_(bridge)#Set_of_boards
        dealer = (board_number - 1) % 4 + 1
        only_ns_vuln = board_number in (2, 5, 12, 15)
        only_ew_vuln = board_number in (3, 6, 9, 16)
        all_vuln = board_number in (4, 7, 10, 13)

        return self.create_with_deck(
            ns_vulnerable=only_ns_vuln or all_vuln,
            ew_vulnerable=only_ew_vuln or all_vuln,
            dealer=dealer,
            deck=deck,
        )

    def create_with_deck(
        self,
        *,
        ns_vulnerable: bool,
        ew_vulnerable: bool,
        dealer: int,
        deck: list[Card],
    ) -> Board:
        def deserialize_hand(cards: list[Card]) -> str:
            # sorted only so that they look purty in the Admin site.
            return "".join([c.serialize() for c in sorted(cards)])

        north_cards = deserialize_hand(deck[0:13])
        east_cards = deserialize_hand(deck[13:26])
        south_cards = deserialize_hand(deck[26:39])
        west_cards = deserialize_hand(deck[39:52])

        return self.create(
            ns_vulnerable=ns_vulnerable,
            ew_vulnerable=ew_vulnerable,
            dealer=dealer,
            north_cards=north_cards,
            east_cards=east_cards,
            south_cards=south_cards,
            west_cards=west_cards,
        )

    def create(self, *args, **kwargs):
        from app.serializers import BoardSerializer

        rv = super().create(*args, **kwargs)

        # nobody (yet) cares about the creation of a new board, but what the heck.
        # I'm just testing out this scheme of using drf to serialize the data.

        send_event(
            channel="top-sekrit-board-creation-channel",
            event_type="message",
            data={
                "new-board": BoardSerializer(rv).data,
            },
        )

        return rv


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

    north_cards = models.CharField(max_length=26)
    east_cards = models.CharField(max_length=26)
    south_cards = models.CharField(max_length=26)
    west_cards = models.CharField(max_length=26)

    def __str__(self):
        if self.ns_vulnerable and self.ew_vulnerable:
            vuln = "Both sides"
        elif not self.ns_vulnerable and not self.ew_vulnerable:
            vuln = "Neither side"
        elif self.ns_vulnerable:
            vuln = "North/South"
        else:
            vuln = "East/West"

        return f"Board #{self.id}, {vuln} vulnerable, dealt by {self.fancy_dealer}"

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


admin.site.register(Board)
