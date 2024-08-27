from bridge.card import Card
from bridge.contract import Bid
from django.contrib import admin
from django.db import models


class HandRecord(models.Model):
    # The "when", and, when combined with knowledge of who dealt, the "who"
    id = models.BigAutoField(
        primary_key=True
    )  # it's the default, but it can't hurt to be explicit.

    # The "where"
    table = models.ForeignKey("Table", on_delete=models.CASCADE)

    # The "what" is in our implicit "call_set" and "play_set" attributes.

    @property
    def most_recent_call(self):
        return self.call_set.order_by("-id").first()

    @property
    def most_recent_bid(self):
        return (
            self.call_set.order_by("-id")
            .annotate(first=models.F("serialized")[0])
            .filter(first__in="1234567")
            .first()
        )

    @property
    def calls(self):
        return self.call_set.order_by("id")

    @property
    def plays(self):
        return self.play_set.order_by("id")

    def __str__(self):
        return f"Auction: {';'.join([str(c) for c in self.calls])}\nPlay: {';'.join([str(p) for p in self.plays])}"


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

    @property
    def libraryCall(self):
        return Bid.deserialize(self.serialized)

    def __str__(self):
        call = Bid.deserialize(self.serialized)
        return f"Call #{self.id}: Someone at {self.hand.table} says {self.serialized=} which means {call}"


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
        return f"Mystery player at {self.hand.table} played {self.serialized} which means {play}"


admin.site.register(Play)
