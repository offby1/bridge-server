from __future__ import annotations

import dataclasses
import logging
import random
from typing import TYPE_CHECKING

from bridge.card import Card as libCard
from bridge.card import Suit as libSuit
from bridge.table import Hand as libHand
from bridge.table import Player as libPlayer
from bridge.table import Table as libTable
from django.contrib import admin
from django.db import models, transaction
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.html import format_html
from django_eventstream import send_event  # type: ignore

from . import SEAT_CHOICES
from .board import Board
from .handaction import HandAction
from .player import Player
from .seat import Seat
from .utils import assert_type

if TYPE_CHECKING:
    import bridge.seat
    from bridge.auction import Auction as libAuction
    from bridge.seat import Seat as libSeat

logger = logging.getLogger(__name__)


class TableException(Exception):
    pass


class TableManager(models.Manager):
    def get_nonfull(self):
        return self.annotate(num_seats=models.Count("seat")).filter(num_seats__lt=4)

    def create_with_two_partnerships(self, p1, p2, shuffle_deck=True):
        t = self.create()
        try:
            with transaction.atomic():
                for seat, player in zip(SEAT_CHOICES, (p1, p2, p1.partner, p2.partner)):
                    Seat.objects.create(
                        direction=seat,
                        player=player,
                        table=t,
                    )
        except Exception as e:
            raise TableException from e

        deck = libCard.deck()

        if shuffle_deck:
            random.shuffle(deck)

        b = Board.objects.create_from_deck_and_board_number(
            board_number=Board.objects.count() + 1,
            deck=deck,
        )

        HandAction.objects.create(board=b, table=t)

        send_event(
            channel="all-tables",
            event_type="message",
            data={
                "table": t.pk,
                "seats": [s.jsonable for s in t.seat_set.all()],
                "action": "just formed",
            },
        )

        return t


"""
These dataclasses are here to make life easy for the table view, and to be testable.  They conveniently collect most of the information that the view will need to display player's hands -- in fact, they collect everything *that this model knows about*.  Stuff that we *don't* know about, but which the view does, are: who is looking at the browser, are they human, &c

I hope they will let me greatly simplify four_hands_partial_view and _four_hands_context_for_table.
"""


@dataclasses.dataclass
class AnnotatedCard:
    card: libCard
    legal_now: bool


@dataclasses.dataclass
class SuitHolding:
    cards_by_suit: dict[libSuit, list[AnnotatedCard]]


@dataclasses.dataclass
class DisplayThingy:
    textual_summary: str
    suit_holdings_by_seat: dict[bridge.seat.Seat, SuitHolding]


# What, no fields?  Well, Django supplies a primary key for us; and more importantly, it will put a "seat_set" attribute
# onto each instance.
class Table(models.Model):
    seat_set: models.Manager[Seat]
    handaction_set: models.Manager[HandAction]

    objects = TableManager()

    def __getitem__(self, seat: libSeat) -> libPlayer:
        modelPlayer = self.players_by_direction[seat.value]
        return modelPlayer.libraryThing

    def modPlayer_by_seat(self, seat: libSeat) -> Player:
        return Player.objects.get_by_name(self[seat].name)

    @cached_property
    def seats(self):
        return self.seat_set.select_related("player__user").all()

    def libraryThing(self):
        players = []
        for seat in self.seats:
            name = seat.player_name
            hand = self.current_action.board.cards_for_direction(seat.direction)
            players.append(
                libPlayer(seat=seat.libraryThing, name=name, hand=libHand(cards=hand)),
            )
        return libTable(players=players)

    @property
    def actions(self):
        return self.handaction_set.order_by("id")

    @property
    def current_auction(self) -> libAuction:
        return self.current_action.auction

    @property
    def current_auction_status(self) -> str:
        s = self.current_auction.status
        if s is self.current_auction.Incomplete:
            calls = self.current_auction.player_calls
            calls_description = "no calls"
            if calls:
                last = calls[-1]
                plural_suffix = "" if len(calls) == 1 else "s"
                calls_description = (
                    f"{len(calls)} call{plural_suffix}; last was {last.call} by {last.player}"
                )
            return calls_description
        return str(s)

    @cached_property
    def current_action(self) -> HandAction:
        rv = self.handaction_set.order_by("-id").first()
        assert rv is not None
        return rv

    @property
    def dealer(self):
        return self.current_board.dealer

    @property
    def declarer(self) -> Seat | None:
        if self.current_action.declarer is None:
            return None
        modelSeat = self.current_action.declarer.seat
        return Seat.objects.get(direction=modelSeat.value, table=self)

    @property
    def dummy(self) -> Seat | None:
        if self.current_action.dummy is None:
            return None
        modelSeat = self.current_action.dummy.seat
        return Seat.objects.get(direction=modelSeat.value, table=self)

    @cached_property
    def dealt_cards_by_seat(self) -> dict[Seat, list[libCard]]:
        rv: dict[Seat, list[libCard]] = {}
        board = self.current_board
        if board is None:
            return rv
        for s in self.seats:
            if s.player is not None:
                rv[s] = board.cards_for_direction(s.direction)

        return rv

    def display_skeleton(self) -> DisplayThingy:
        return DisplayThingy(textual_summary="htf do I know", suit_holdings_by_seat={})

    @property
    def current_cards_by_seat(self) -> dict[Seat, set[libCard]]:
        rv = {}
        for seat, cardlist in self.dealt_cards_by_seat.items():
            assert_type(seat, Seat)
            assert_type(cardlist, list)

            rv[seat] = set(cardlist)

        if self.current_auction.found_contract:
            model_seats_by_lib_seats = {}
            for _index, libseat, card, _is_winner in self.current_action.annotated_plays:
                if libseat not in model_seats_by_lib_seats:
                    model_seats_by_lib_seats[libseat] = self.current_action.seat_from_libseat(
                        libseat,
                    )
                seat = model_seats_by_lib_seats[libseat]
                assert_type(seat, Seat)
                rv[seat].remove(card)

        return rv

    @property
    def current_board(self):
        return self.current_action.board

    @property
    def players_by_direction(self):
        return {s.direction: s.player for s in self.seats}

    @property
    def next_seat_to_play(self) -> Seat | None:
        if self.current_auction.found_contract:
            xscript = self.current_action.xscript
            return Seat.objects.get(table=self, direction=xscript.player.seat.value)

        return None

    def as_link(self):
        return format_html(
            "<a href='{}'>{}</a>",
            reverse("app:table-detail", kwargs={"pk": self.pk}),
            str(self),
        )

    def as_tuples(self):
        return [(SEAT_CHOICES[d], p) for d, p in self.players_by_direction.items()]

    def is_empty(self):
        return all(p is None for p in self.players_by_direction.values())

    def is_full(self):
        return all(p is not None for p in self.players_by_direction.values())

    def __str__(self):
        return f"Table {self.id}"


admin.site.register(Table)
