import bridge
from django.contrib import admin
from django.db import models

from . import SEAT_CHOICES
from .table import Table


class SeatException(Exception):
    pass


class Seat(models.Model):
    direction = models.SmallIntegerField(
        choices=SEAT_CHOICES,
    )
    player = models.OneToOneField("Player", null=True, on_delete=models.CASCADE)
    table = models.ForeignKey(Table, on_delete=models.CASCADE)

    def partner_with(self, other):
        if self.player is None:
            raise SeatException(
                f"Cannot partner {self=} with {other=} because {self.player=} is None",
            )

        if other.player is None:
            raise SeatException(
                f"Cannot partner {self=} with {other=} because {other.player=} is None",
            )

        if self.player.partner is not None:
            raise SeatException(
                f"Cannot partner {self=} with {other=} because {self.player.partner=} is already partnered up",
            )
        if other.player.partner is not None:
            raise SeatException(
                f"Cannot partner {self=} with {other=} because {other.player.partner=} is already partnered up",
            )

        self.player.partner_with(other.player)

    def library_object_thingy(self):
        return bridge.seat.Seat(self.direction)

    def save(self, *args, **kwargs):
        lot = self.library_object_thingy()

        partner_direction = lot.partner()
        partner_seat = Seat.objects.filter(
            direction=partner_direction.value,
            table=self.table,
        ).first()

        if self.player is not None and partner_seat is not None and partner_seat.player is not None:
            self.partner_with(partner_seat)

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{SEAT_CHOICES[self.direction]} at {self.table=}"

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["player", "table"],
                name="no_more_than_one_player_per_table",
            ),
            models.UniqueConstraint(
                fields=["direction", "table"],
                name="no_more_than_four_directions_per_table",
            ),
            models.CheckConstraint(
                name="%(app_label)s_%(class)s_direction_valid",
                condition=models.Q(direction__in=SEAT_CHOICES),
            ),
        ]


admin.site.register(Seat)
