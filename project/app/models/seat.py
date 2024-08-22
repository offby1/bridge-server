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

    def others_at_table(self):
        return self.table.seat_set.exclude(direction=self.direction)

    def __str__(self):
        return f"{SEAT_CHOICES[self.direction]} at {self.table}"

    def _check_table_consistency(self):
        if self.player is None:
            return
        if self.table is None:
            return
        if self.player.partner is None:
            raise SeatException(f"Whoa thar friend; {self.player} has no partner!!")

        if self.player.partner.table is None:
            return

        if self.table is None:
            return

        if self.player.partner.table != self.table:
            raise SeatException(
                f"Whoa thar friend {self.player}'s partner {self.player.partner} is already seated at {self.player.partner.table} but this is {self.table}!!",
            )

    def save(self, *args, **kwargs):
        self._check_table_consistency()
        super().save(*args, **kwargs)

    class Meta:
        ordering = ["direction"]
        constraints = [
            models.CheckConstraint(
                name="%(app_label)s_%(class)s_direction_valid",
                condition=models.Q(direction__in=SEAT_CHOICES),
            ),
            models.UniqueConstraint(
                fields=["player"],
                name="%(app_label)s_%(class)s_no_more_than_one_seat_per_player",
            ),
            models.UniqueConstraint(
                fields=["direction", "table"],
                name="%(app_label)s_%(class)s_no_more_than_four_directions_per_table",
            ),
        ]


admin.site.register(Seat)
