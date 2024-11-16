from __future__ import annotations

import logging
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
from django_eventstream import send_event  # type: ignore [import-untyped]

from app.models.board import Board
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
        self, p1: Player, p2: Player, shuffle_deck: bool = True, desired_board_pk: int | None = None
    ) -> Table:
        try:
            with transaction.atomic():
                t: Table = self.create()
                for seat, player in zip(SEAT_CHOICES, (p1, p2, p1.partner, p2.partner)):
                    modelSeat.objects.create(
                        direction=seat,
                        player=player,
                        table=t,
                    )

                t.next_board(shuffle_deck=shuffle_deck, desired_board_pk=desired_board_pk)
        except Exception as e:
            raise TableException(str(e)) from e

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

    tempo_seconds = models.FloatField(
        default=1.0,
        db_comment="Time, in seconds, that the bot will wait before making a call or play",
    )  # type: ignore

    summary_for_this_viewer: tuple[str, str | int]

    def gimme_dat_fresh_tempo(self):
        if hasattr(self, "tempo_seconds"):
            del self.tempo_seconds
        return self.tempo_seconds

    @cached_property
    def seats(self):
        return self.seat_set.select_related("player__user").all()

    @property
    def current_auction(self) -> libAuction:
        return self.current_hand.auction

    @property
    def current_hand(self) -> Hand:
        rv = self.hand_set.order_by("-id").first()
        assert rv is not None
        return rv

    # Seems dumb, but I don't know how else to get this information into a DRF serializer
    def current_hand_pk(self) -> int:
        return self.current_hand.pk

    @property
    def hand_is_complete(self) -> bool:
        return self.current_hand.is_complete

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

    # BUGBUG -- the semantics are wrong.  Currently this does "get the next board that hasn't been played at this table",
    # but it should do "get the next board that none of this table's players have played".
    def next_board(self, *, shuffle_deck=True, desired_board_pk: int | None = None) -> Board:
        if self.hand_set.exists() and not self.hand_is_complete:
            msg = f"Naw, {self} isn't complete; no next board for you"
            raise TableException(msg)

        with transaction.atomic():
            if desired_board_pk is not None:
                b = Board.objects.get(pk=desired_board_pk)
            else:
                b = self.find_unplayed_board()
            if b is None:
                deck = bridge.card.Card.deck()

                b = Board.objects.create_from_deck(
                    deck=deck,
                    shuffle_deck=shuffle_deck,
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


@admin.register(Table)
class TableAdmin(admin.ModelAdmin):
    list_display = ["__str__", "tempo_seconds"]
