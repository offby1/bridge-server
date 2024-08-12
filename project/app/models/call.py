from bridge.contract import Bid
from django.contrib import admin
from django.db import models


class Call(models.Model):
    # The "who"
    seat = models.ForeignKey("Seat", on_delete=models.CASCADE)

    @property
    def player(self):
        return self.seat.player

    # Now, the "what":
    # pass, bid, double, redouble

    serialized = models.CharField(
        max_length=10,
        db_comment="A short string with which we can create a bridge.contract.Call object",
    )

    def __str__(self):
        call = Bid.deserialize(self.serialized)
        return f"{self.player} ({self.seat.direction} at {self.seat.table}) says {self.serialized} which means {call}"


admin.site.register(Call)
