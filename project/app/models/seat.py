import logging
from typing import TYPE_CHECKING

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
    def create(self, *args, **kwargs):
        rv = super().create(*args, **kwargs)
        player: Player = rv.player
        player.toggle_bot(player.allow_bot_to_play_for_me)
        return rv


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
        return f"Model seat {vars(self)}"

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

    def _check_table_consistency(self):
        if self.player is None:
            return
        if self.table is None:
            return
        if self.player.partner is None:
            msg = f"Whoa thar friend; {self.player} has no partner!!"
            raise SeatException(msg)

        if self.player.partner.current_table is None:
            return

        if self.table is None:
            return

        if self.player.partner.current_table != self.table:
            msg = f"Whoa thar friend {self.player}'s partner {self.player.partner} is already seated at {self.player.partner.current_table} but this is {self.table}!!"
            raise SeatException(
                msg,
            )

    def save(self, *args, **kwargs):
        with transaction.atomic():
            self._check_table_consistency()
            super().save(*args, **kwargs)
            self.player.currently_seated = True
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
