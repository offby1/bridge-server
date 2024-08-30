import itertools

from bridge.auction import Auction
from bridge.card import Card
from bridge.contract import Bid
from bridge.seat import Seat
from bridge.table import Player
from django.contrib import admin
from django.db import models
from django.utils.functional import cached_property


class HandRecord(models.Model):
    # The "when", and, when combined with knowledge of who dealt, the "who"
    id = models.BigAutoField(
        primary_key=True
    )  # it's the default, but it can't hurt to be explicit.

    # The "where"
    table = models.ForeignKey("Table", on_delete=models.CASCADE)

    # The "what" is in our implicit "call_set" and "play_set" attributes, along with this board.
    board = models.OneToOneField("Board", on_delete=models.CASCADE)

    @cached_property
    def auction(self):
        rv = Auction(table=self.table, dealer=self.board.dealer)
        for index, seat, call in self.annotated_calls:
            print(f"{rv=}")
            print(f"{seat=}")
            player = Player(seat=seat, name="wtf", hand="whaaaat")
            print(f"{player=}")
            print(f"{call=}")
            rv.append_located_call(player, call)
        return rv

    @property
    def declarer(self):
        return self.auction.declarer

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
    def annotated_calls(self) -> list[tuple[int, Seat, "Call"]]:
        seat_cycle = Seat.cycle()
        while True:
            s = next(seat_cycle)

            if s.value == self.board.dealer:
                break
        # I *think* the first call is made by dealer's LHO :-)
        return zip(itertools.count(1), seat_cycle, self.calls.all())

    @property
    def annotated_plays(self):
        seat_cycle = Seat.cycle()
        while True:
            s = next(seat_cycle)

            if s.value == self.declarer.lho:
                break

        return zip(itertools.count(1), seat_cycle, self.plays.all())

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
        return str(self.libraryCall)


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

    # TODO -- a constraint that says a given card must appear no more than once in a given handrecord


admin.site.register(Play)
