from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, MutableMapping

import bridge.seat
from django.contrib import admin
from django.db import models, transaction
from django.db.models.expressions import RawSQL
from django.utils.functional import cached_property

from .common import SEAT_CHOICES

if TYPE_CHECKING:
    from . import Player, Table  # noqa


logger = logging.getLogger(__name__)


class SeatException(Exception):
    pass


class SeatManager(models.Manager):
    @staticmethod
    def _update_player(seat: Seat) -> None:
        seat.player.current_seat = seat
        seat.player._control_bot()
        seat.player.save()
        seat._check_consistency()
        logger.debug(
            "New or update seat! %s %s at table #%s",
            seat.player.name,
            seat.direction,
            seat.table.display_number,
        )

    def create(self, *args, **kwargs) -> Seat:
        rv = super().create(*args, **kwargs)
        self._update_player(rv)
        return rv

    def update_or_create(
        self, defaults: MutableMapping[str, Any] | None = None, **kwargs: Any
    ) -> tuple[Any, bool]:
        rv1, rv2 = super().update_or_create(defaults, **kwargs)
        self._update_player(rv1)
        return rv1, rv2


class Seat(models.Model):
    objects = SeatManager()

    direction = models.CharField(
        choices=SEAT_CHOICES.items(),
    )

    player = models.ForeignKey["Player"](
        "Player",
        on_delete=models.CASCADE,
        related_name="historical_seat_set",
        db_comment="this is None *only* if this player has *never* been seated.  Use `Player.currently_seated` for most things.",
    )  # type: ignore [call-overload]
    table = models.ForeignKey["Table"]("Table", on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.named_direction} at {self.table}"

    def __repr__(self):
        return str(self) + f" ({self.player.name})"

    @cached_property
    def player_name(self):
        return self.player.name

    @property
    def jsonable(self):
        return {
            "direction": self.direction,
            "player": self.player.pk,
            "table": self.table.pk,
        }

    def others_at_table(self):
        return self.table.seat_set.exclude(direction=self.direction)

    @property
    def libraryThing(self):
        return bridge.seat.Seat(self.direction)

    @property
    def named_direction(self):
        return SEAT_CHOICES[self.direction]

    def _check_consistency(self):
        if self.player is None:
            logger.warning(f"{self}: no player, no problem")
            return
        if self.table is None:
            return
        if self.player.partner is None:
            msg = f"Whoa thar friend; {self.player} has no partner!!"
            raise SeatException(msg)

        if self.player.partner.current_table is None:
            return

        if self.player.partner.current_table != self.table:
            msg = f"Whoa thar friend {self.player}'s partner {self.player.partner} is already seated at {self.player.partner.current_table} but this is {self.table}!!"
            raise SeatException(
                msg,
            )

        if self.player.current_seat not in (None, self):
            msg = f"Uh, {self.player.current_seat=} but I am {self=}"
            raise SeatException(
                msg,
            )

        logger.warning(f"Everything looks good -- {self.player.name=}'s current_seat is me")

    def save(self, *args, **kwargs):
        with transaction.atomic():
            self._check_consistency()
            super().save(*args, **kwargs)
            self.player.current_seat = self
            self.player.save()

    class Meta:
        ordering = [RawSQL("position(DIRECTION in 'NESW')", params=[])]

        constraints = [
            models.CheckConstraint(  # type: ignore
                name="%(app_label)s_%(class)s_direction_valid",
                condition=models.Q(direction__in=SEAT_CHOICES),
            ),
            models.UniqueConstraint(
                fields=["direction", "table"],
                name="%(app_label)s_%(class)s_no_more_than_four_directions_per_table",
            ),
        ]


admin.site.register(Seat)
