from __future__ import annotations

from collections.abc import Generator
import logging
import time
from typing import TYPE_CHECKING

import bridge.card
import bridge.seat
from django.contrib import admin
from django.db import models, transaction
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.html import format_html
from django_eventstream import send_event  # type: ignore [import-untyped]

from app.models.common import SEAT_CHOICES
from app.models.hand import Hand
from app.models.seat import Seat as modelSeat
from app.models.tournament import Tournament
from app.models.types import PK
from app.utils import movements

if TYPE_CHECKING:
    import bridge.table
    from bridge.auction import Auction as libAuction

    from app.models.player import Player, Seat


logger = logging.getLogger(__name__)


class TableException(Exception):
    pass


class NoMoreBoards(Exception):
    pass


class RoundIsOver(NoMoreBoards):
    pass


class TournamentIsComplete(NoMoreBoards):
    pass


class TableHasNoHand(TableException):
    pass


class TableManager(models.Manager):
    def create(self, *args, **kwargs) -> Table:
        tournament = kwargs["tournament"]
        max_ = (
            self.filter(tournament=tournament).aggregate(models.Max("display_number"))[
                "display_number__max"
            ]
            or 0
        )
        display_number = max_ + 1
        kwargs.setdefault("display_number", display_number)
        rv = super().create(*args, **kwargs)
        assert rv.seat_set.count() in {0, 4}
        return rv

    def create_with_two_partnerships(
        self, p1: Player, p2: Player, tournament: Tournament | None = None, **kwargs
    ) -> Table:
        with transaction.atomic():
            t: Table = self.create(tournament=tournament, **kwargs)
            logger.debug("Created %s", t)
            if p1.partner is None or p2.partner is None:
                raise TableException(
                    f"Cannot create a table with players {p1} and {p2} because at least one of them lacks a partner "
                )
            player_pks = set(p.pk for p in (p1, p2, p1.partner, p2.partner))
            if len(player_pks) != 4:
                raise TableException(
                    f"Cannot create a table with players {player_pks} --we need exactly four"
                )
            for seat, player in zip(SEAT_CHOICES, (p1, p2, p1.partner, p2.partner)):
                modelSeat.objects.create(
                    direction=seat,
                    player=player,
                    table=t,
                )

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

    def create_for_tournament(self, tournament) -> Generator[Table]:
        movement = tournament.get_movement()
        for tn in sorted(movement.table_settings_by_table_number.keys()):
            table, created = self.get_or_create(display_number=tn + 1, tournament=tournament)
            logger.debug(f"{created=} {table}")
            yield table


class Table(models.Model):
    seat_set: models.Manager[modelSeat]
    hand_set: models.Manager[Hand]

    objects = TableManager()

    tempo_seconds = models.FloatField(
        default=1.0,
        db_comment="Time, in seconds, that the bot will wait before making a call or play",
    )  # type: ignore

    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE)

    display_number = models.SmallIntegerField()

    # View code adds these
    summary_for_this_viewer: tuple[str, str | int]
    played_hands_string: str

    def next_hand_for_this_round(self, settings: movements.PlayersAndBoardsForOneRound):
        hand_count = self.hand_set.filter(
            board__group=settings.board_group.letter
        ).count()  # assume they're all complete
        board = settings.board_group.boards[hand_count]
        from app.models import Player, Seat

        def ensure_player_at_seat(*, direction: str, player: Player) -> None:
            current_seat = getattr(player, "current_seat", None)

            if current_seat is None:
                logger.debug(f"{current_seat=} so we gotta get to work")
            elif current_seat.table != self:
                logger.debug(f"{current_seat.table=} != {self=} so we gotta get to work")
            elif current_seat.direction != direction:
                logger.debug(f"{current_seat.direction=} != {direction=} so we gotta get to work")
            else:
                logger.debug(
                    f"{player} is already sitting {direction=}  at {self}; no need to do anything"
                )
                return

            player.unseat_me()
            seat, created = Seat.objects.update_or_create(
                player=player, defaults={"direction": direction, "table": self}
            )
            logger.info(f"{created=} {seat} {seat.player_name}")

        ensure_player_at_seat(
            direction="N", player=Player.objects.get(pk=settings.quartet.ns.id_[0])
        )
        ensure_player_at_seat(
            direction="S", player=Player.objects.get(pk=settings.quartet.ns.id_[1])
        )
        ensure_player_at_seat(
            direction="E", player=Player.objects.get(pk=settings.quartet.ew.id_[0])
        )
        ensure_player_at_seat(
            direction="W", player=Player.objects.get(pk=settings.quartet.ew.id_[1])
        )
        new_hand = Hand.objects.create(board=board, table=self)
        logger.debug("Table %s now has a new hand: %s", self.pk, new_hand.pk)
        for channel in (
            self.event_channel_name,
            *[s.player.event_channel_name for s in self.current_seats()],
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

    @property
    def event_channel_name(self):
        return f"table:{self.pk}"

    @cached_property
    def all_seats(self) -> models.QuerySet:
        """
        After filtering this or whatever, be sure to take a slice of the first four items
        """
        return self.seat_set.order_by("-id").select_related("player__user")

    def current_seats(self) -> list[Seat]:
        return sorted(self.all_seats.all()[0:4], key=lambda s: "NESW".index(s.direction))

    def unseat_players(self, *, reason=None) -> None:
        seat: modelSeat
        victim_names = []
        logger.debug("Unseating players from table #%s", self.display_number)
        for seat in self.seat_set.filter(direction__in="NE"):
            seat.player.unseat_partnership(reason=reason)
            victim_names.append(seat.player.name)
            victim_names.append(seat.player.partner.name)
        if victim_names:
            logger.debug("Unseated %s from table #%s", ", ".join(victim_names), self.display_number)
        else:
            logger.warning("Hmm, table #%s has no seats?", self.display_number)
            for s in modelSeat.objects.all():
                logger.warning(
                    "%s sits %s at table #%s", s.player.name, s.direction, s.table.display_number
                )

    @property
    def current_auction(self) -> libAuction:
        return self.current_hand.auction

    @property
    def has_hand(self) -> bool:
        return self.hand_set.exists()

    @property
    def current_hand(self) -> Hand:
        rv = self.hand_set.order_by("-id").first()
        if rv is None:
            msg = f"{self} has no hands"
            raise TableHasNoHand(msg)
        return rv

    def current_hand_pk(self) -> PK:
        return self.current_hand.pk

    @property
    def hand_is_complete(self) -> bool:
        rv = self.current_hand.is_complete
        logger.debug("%s", f"{self.current_hand=} {self.current_hand.is_complete=}")
        return rv

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
        for s in self.current_seats():
            if s.player is not None:
                rv[s] = board.cards_for_direction(s.direction)

        return rv

    def played_hands_count(self) -> tuple[int, bool]:
        # https://www.better-simple.com/django/2025/01/01/complex-django-filters-with-subquery/ might help
        completed = 0
        in_progress = 0
        h: Hand
        for h in Hand.objects.filter(table=self):
            if h.is_complete:
                completed += 1
            else:
                in_progress += 1
        return (completed, in_progress > 0)

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
        if self.has_hand:
            return format_html(
                "<a href='{}'>{}</a>",
                reverse("app:hand-detail", kwargs={"pk": self.current_hand.pk}),
                str(self),
            )
        return format_html("At {}, waiting for a board!!", self)

    def as_tuples(self):
        return [(SEAT_CHOICES[d], p) for d, p in self.current_hand.players_by_direction.items()]

    def is_empty(self):
        return all(p is None for p in self.players_by_direction.values())

    def is_full(self):
        return all(p is not None for p in self.players_by_direction.values())

    def __repr__(self):
        return f"Table #{self.display_number} (pk {self.pk}) in tournament #{self.tournament.display_number}"

    __str__ = __repr__

    class Meta:
        constraints = [
            models.UniqueConstraint(  # type: ignore[call-arg]
                name="%(app_label)s_%(class)s_display_number_unique_per_tournament",
                fields=["display_number", "tournament_id"],
            ),
        ]


@admin.register(Table)
class TableAdmin(admin.ModelAdmin):
    list_display = ["__str__", "tempo_seconds"]
