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
