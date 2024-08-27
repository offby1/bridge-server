from bridge.card import Card
from bridge.contract import Bid
from django.contrib import admin
from django.db import models


class HandRecord(models.Model):
    id = models.BigAutoField(
        primary_key=True
    )  # it's the default, but it can't hurt to be explicit.

    # The "who" (including the "where" and maybe even "when")
    seat = models.ForeignKey("Seat", on_delete=models.CASCADE)

    @property
    def player(self):
        return self.seat.player


admin.site.register(HandRecord)


class Call(models.Model):
    id = models.BigAutoField(
        primary_key=True
    )  # it's the default, but it can't hurt to be explicit.

    hand = models.ForeignKey(HandRecord, on_delete=models.CASCADE)
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


class Play(models.Model):
    id = models.BigAutoField(
        primary_key=True
    )  # it's the default, but it can't hurt to be explicit.

    hand = models.ForeignKey(HandRecord, on_delete=models.CASCADE)

    serialized = models.CharField(
        max_length=2,
        db_comment="A short string with which we can create a bridge.card.Card object",
    )

    def __str__(self):
        play = Card.deserialize(self.serialized)
        return f"{self.player} ({self.seat.direction} at {self.seat.table}) played {self.serialized} which means {play}"


admin.site.register(Play)
