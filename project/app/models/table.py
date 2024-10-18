from __future__ import annotations

import logging
import random
import time
from typing import TYPE_CHECKING

import bridge.card
import bridge.seat
import bridge.table
from django.contrib import admin
from django.db import models, transaction
from django.db.models.expressions import RawSQL
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.html import format_html
from django_eventstream import send_event  # type: ignore

from app.models.board import TOTAL_BOARDS, Board
from app.models.common import SEAT_CHOICES
from app.models.hand import Hand
from app.models.seat import Seat as modelSeat

if TYPE_CHECKING:
    from bridge.auction import Auction as libAuction
    from django.db.models.query import QuerySet

    from app.models.player import Player


logger = logging.getLogger(__name__)


class TableException(Exception):
    pass


class TableManager(models.Manager):
    def get_nonfull(self):
        return self.annotate(num_seats=models.Count("seat")).filter(num_seats__lt=4)

    def create_with_two_partnerships(
        self, p1: Player, p2: Player, shuffle_deck: bool = True
    ) -> Table:
        t: Table = self.create()
        try:
            with transaction.atomic():
                for seat, player in zip(SEAT_CHOICES, (p1, p2, p1.partner, p2.partner)):
                    modelSeat.objects.create(
                        direction=seat,
                        player=player,
                        table=t,
                    )
        except Exception as e:
            raise TableException from e

        t.next_board(shuffle_deck=shuffle_deck)

        send_event(
            channel="all-tables",
            event_type="message",
            data={
                "table": t.pk,
                "seats": [s.jsonable for s in t.seat_set.all()],
                "action": "just formed",
                "time": time.time(),
            },
        )

        return t


# What, no fields?  Well, Django supplies a primary key for us; and more importantly, it will put a "seat_set" attribute
# onto each instance.
class Table(models.Model):
    seat_set: models.Manager[modelSeat]
    hand_set: models.Manager[Hand]

    objects = TableManager()

    @cached_property
    def seats(self):
        return self.seat_set.select_related("player__user").all()

    @cached_property
    def libraryThing(self):
        players = []
        for seat in self.seats:
            name = seat.player_name
            hand = self.current_hand.board.cards_for_direction(seat.direction)
            players.append(
                bridge.table.Player(
                    seat=seat.libraryThing, name=name, hand=bridge.table.Hand(cards=hand)
                ),
            )
        return bridge.table.Table(players=players)

    @cached_property
    def current_auction(self) -> libAuction:
        return self.current_hand.auction

    @cached_property
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
    def current_hand(self) -> Hand:
        rv = self.hand_set.order_by("-id").first()
        assert rv is not None
        return rv

    @property
    def hand_is_complete(self) -> bool:
        h = self.current_hand
        if h is None:
            return False
        # TODO -- replace the 52 with ... something?  Probably the count of cards in the current board.
        return self.current_hand.play_set.count() == 52

    @property
    def dealer(self):
        return self.current_board.dealer

    @property
    def declarer(self) -> modelSeat | None:
        if self.current_hand.declarer is None:
            return None

        return modelSeat.objects.get(direction=self.current_hand.declarer.seat.value, table=self)

    @property
    def dummy(self) -> modelSeat | None:
        if self.current_hand.dummy is None:
            return None
        return modelSeat.objects.get(direction=self.current_hand.dummy.seat.value, table=self)

    @cached_property
    def dealt_cards_by_seat(self) -> dict[modelSeat, list[bridge.card.Card]]:
        rv: dict[modelSeat, list[bridge.card.Card]] = {}
        board = self.current_board
        if board is None:
            return rv
        for s in self.seats:
            if s.player is not None:
                rv[s] = board.cards_for_direction(s.direction)

        return rv

    def played_boards(self) -> QuerySet:
        return Board.objects.filter(
            pk__in=RawSQL(
                """
                SELECT
                        APP_BOARD.ID
                FROM
                        PUBLIC.APP_TABLE
                        JOIN PUBLIC.APP_HAND ON APP_HAND.TABLE_ID = APP_TABLE.ID
                        JOIN PUBLIC.APP_BOARD ON APP_BOARD.ID = APP_HAND.BOARD_ID
                WHERE
                        APP_TABLE.ID = %s
        """,
                (self.pk,),
            )
        )

    def find_unplayed_board(self) -> Board | None:
        unplayed_boards = Board.objects.exclude(pk__in=self.played_boards()).order_by("id")

        return unplayed_boards.first()

    def next_board(self, *, shuffle_deck=True) -> Board:
        b = self.find_unplayed_board()
        if b is None:
            if Board.objects.count() >= TOTAL_BOARDS:
                msg = "No more tables! The tournament is over."
                raise TableException(msg)

            deck = bridge.card.Card.deck()

            if shuffle_deck:
                random.shuffle(deck)

            b = Board.objects.create_from_deck(
                deck=deck,
            )
        Hand.objects.create(board=b, table=self)

        return b

    @property
    def current_board(self):
        return self.current_hand.board

    @property
    def next_seat_to_play(self) -> modelSeat | None:
        if self.current_auction.found_contract:
            xscript = self.current_hand.get_xscript()
            return modelSeat.objects.get(
                table=self, direction=xscript.current_named_seat().seat.value
            )

        return None

    def as_link(self):
        return format_html(
            "<a href='{}'>{}</a>",
            reverse("app:hand-detail", kwargs={"pk": self.current_hand.pk}),
            str(self),
        )

    def as_tuples(self):
        return [(SEAT_CHOICES[d], p) for d, p in self.current_hand.players_by_direction.items()]

    def is_empty(self):
        return all(p is None for p in self.players_by_direction.values())

    def is_full(self):
        return all(p is not None for p in self.players_by_direction.values())

    def __str__(self):
        return f"Table {self.id}"


admin.site.register(Table)
