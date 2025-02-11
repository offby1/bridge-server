from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

import bridge.card
import bridge.seat
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
from app.models.tournament import Tournament
from app.models.types import PK

if TYPE_CHECKING:
    import bridge.table
    from bridge.auction import Auction as libAuction
    from django.db.models.query import QuerySet

    from app.models.player import Player


logger = logging.getLogger(__name__)


class TableException(Exception):
    pass


class NoMoreBoards(Exception):
    pass


class TableManager(models.Manager):
    def create(self, *args, **kwargs) -> Table:
        if "tournament" not in kwargs:
            tournament, _ = Tournament.objects.get_or_create_running_tournament()
            kwargs["tournament"] = tournament
        return super().create(*args, **kwargs)

    def create_with_two_partnerships(self, p1: Player, p2: Player) -> Table:
        try:
            with transaction.atomic():
                t: Table = self.create()
                logger.debug("Created %s, tournament %s", t, t.tournament)
                if p1.partner is None or p2.partner is None:
                    raise TableException(
                        f"Cannot create a table with players {p1} and {p2} because at least one of them lacks a partner "
                    )
                player_pks = set(p.pk for p in (p1, p2, p1.partner, p2.partner))
                if len(player_pks) != 4:
                    raise TableException(
                        f"Cannot create a table with seats {player_pks} --we need exactly four"
                    )
                for seat, player in zip(SEAT_CHOICES, (p1, p2, p1.partner, p2.partner)):
                    modelSeat.objects.create(
                        direction=seat,
                        player=player,
                        table=t,
                    )

                nb = t.next_board()
                if nb is None:
                    logger.warning("I have a bad feeling about this")
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

    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE)

    # View code adds these
    summary_for_this_viewer: tuple[str, str | int]
    played_hands_string: str

    @property
    def event_channel_name(self):
        return f"table:{self.pk}"

    @cached_property
    def seats(self):
        return self.seat_set.select_related("player__user").all()

    @property
    def current_auction(self) -> libAuction:
        return self.current_hand.auction

    @property
    def current_hand(self) -> Hand:
        rv = self.hand_set.order_by("-id").first()
        assert rv is not None, "current_hand can't find no hands"
        return rv

    def current_hand_pk(self) -> PK:
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

    def played_hands_count(self) -> tuple[int, bool]:
        # https://www.better-simple.com/django/2025/01/01/complex-django-filters-with-subquery/ might help
        completed = 0
        in_progress = 0
        for h in Hand.objects.filter(table=self):
            if h.is_complete:
                completed += 1
            else:
                in_progress += 1
        return (completed, in_progress > 0)

    def find_unplayed_board(self) -> Board | None:
        seats = self.seat_set.all()

        # What I *really* wanted to write here was `models.Q(False)`, but that doesn't work.
        expression = models.Q(pk__in=[])

        for seat in seats:
            bp = seat.player.boards_played.order_by("id").all()
            logger.debug("Player %s has played %s", seat.player.name, [b.pk for b in bp])
            expression |= models.Q(pk__in=bp)

        assert self.tournament is not None, "find_unplayed_board notes they ain't no tournament"
        unplayed_boards = self.tournament.board_set.exclude(expression)
        return unplayed_boards.first()

    def next_board(self) -> Board:
        with transaction.atomic():
            if self.tournament.is_complete:
                logger.debug(
                    "No need to do fancy queries if we already know the tournament is over."
                )
                raise NoMoreBoards()

            logger.debug("Table %s: someone wants the next board", self.pk)
            if self.hand_set.exists() and not self.hand_is_complete:
                msg = f"Naw, {self} isn't complete; no next board for you"
                logger.warning("%s", msg)
                raise TableException(msg)

            if (b := self.find_unplayed_board()) is None:
                logger.debug(
                    "I guess our caller has played all the boards, and just has to wait 🤷"
                )
                raise NoMoreBoards()

            new_hand = Hand.objects.create(board=b, table=self)
            logger.debug("Table %s now has a new hand: %s", self.pk, new_hand.pk)
            for channel in (
                self.event_channel_name,
                *[s.player.event_channel_name for s in self.seats],
            ):
                send_event(
                    channel=channel,
                    event_type="message",
                    data={
                        "new-hand": new_hand.pk,
                        "time": time.time(),
                        "tempo_seconds": self.tempo_seconds,
                    },
                )

            return b

    @property
    def current_board(self):
        return self.current_hand.board

    @property
    def next_seat_to_play(self) -> modelSeat | None:
        if self.current_auction.found_contract:
            xscript = self.current_hand.get_xscript()
            n = xscript.next_seat_to_play()
            if n is None:
                return None
            return modelSeat.objects.get(table=self, direction=n.value)

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
        return f"Table {self.id} in {self.tournament}"


@admin.register(Table)
class TableAdmin(admin.ModelAdmin):
    list_display = ["__str__", "tempo_seconds"]
