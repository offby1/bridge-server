import itertools

from bridge.auction import Auction
from bridge.card import Card as libCard
from bridge.contract import Bid as libBid
from bridge.seat import Seat as libSeat
from django.contrib import admin
from django.db import models
from django.utils.functional import cached_property

from .utils import assert_type


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
        dealer = libSeat(self.board.dealer)

        libTable = self.table.libraryThing()
        rv = Auction(table=libTable, dealer=dealer)
        for index, seat, call in self.annotated_calls:
            player = libTable.players[seat]
            rv.append_located_call(player=player, call=call.libraryThing)
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

    def seat_from_libseat(self, seat: libSeat):
        assert_type(seat, libSeat)
        return self.table.seat_set.get(direction=seat.value)

    @property
    def calls(self):
        return self.call_set.order_by("id")

    @property
    def annotated_calls(self) -> list[tuple[int, libSeat, "Call"]]:
        seat_cycle = libSeat.cycle()
        while True:
            s = next(seat_cycle)

            if s.lho().value == self.board.dealer:
                break
        # The first call is made by dealer.
        return zip(itertools.count(1), seat_cycle, self.calls.all())

    @property
    def annotated_plays(self):
        seat_cycle = libSeat.cycle()
        while True:
            s = next(seat_cycle)

            if s.lho() == self.declarer.seat:
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
    def libraryThing(self):
        return libBid.deserialize(self.serialized)

    def __str__(self):
        return str(self.libraryThing)


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
        play = libCard.deserialize(self.serialized)
        return f"Mystery player at {self.hand.table} played {self.serialized} which means {play}"

    # TODO -- a constraint that says a given card must appear no more than once in a given handrecord


admin.site.register(Play)
