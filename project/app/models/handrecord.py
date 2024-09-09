import itertools
from typing import TYPE_CHECKING

from bridge.auction import Auction as libAuction
from bridge.card import Card as libCard
from bridge.contract import Bid as libBid
from bridge.contract import Call as libCall
from bridge.seat import Seat as libSeat
from bridge.table import Player as libPlayer
from django.contrib import admin
from django.db import models
from django_eventstream import send_event  # type: ignore

from .utils import assert_type

if TYPE_CHECKING:
    from django.db.models.manager import RelatedManager

    from . import Board, Seat, Table  # noqa


class AuctionException(Exception):
    pass


class HandRecord(models.Model):
    if TYPE_CHECKING:
        call_set = RelatedManager["Call"]()

    # The "when", and, when combined with knowledge of who dealt, the "who"
    id = models.BigAutoField(
        primary_key=True,
    )  # it's the default, but it can't hurt to be explicit.

    # The "where"
    table = models.ForeignKey["Table"]("Table", on_delete=models.CASCADE)

    # The "what" is in our implicit "call_set" and "play_set" attributes, along with this board.
    board = models.OneToOneField["Board"]("Board", on_delete=models.CASCADE)

    def add_call_from_player(self, *, player: libPlayer, call: libCall):
        assert_type(player, libPlayer)
        assert_type(call, libCall)

        auction = self.auction
        try:
            auction.raise_if_illegal_call(player=player, call=call)
        except Exception as e:
            raise AuctionException(str(e)) from e

        self.call_set.create(serialized=call.serialize())

        from app.models import Player

        modelPlayer = Player.objects.get_by_name(player.name)
        # TODO -- this duplicates the (admittedly trivial) `_auction_channel_for_table` in views.table
        for channel in (str(self.table.pk), "all-tables"):
            send_event(
                channel=channel,
                event_type="message",
                data={"table": self.table.pk, "player": modelPlayer.pk, "call": call.serialize()},
            )

    @property
    def auction(self):
        dealer = libSeat(self.board.dealer)

        libTable = self.table.libraryThing()
        rv = libAuction(table=libTable, dealer=dealer)
        for _index, seat, call in self.annotated_calls:
            player = libTable.players[seat]
            rv.append_located_call(player=player, call=call.libraryThing)
        return rv

    @property
    def declarer(self):
        return self.auction.declarer

    @property
    def player_who_may_call(self):
        from . import Player

        if self.auction.status is libAuction.Incomplete:
            libAllowed = self.auction.allowed_caller()
            return Player.objects.get_by_name(libAllowed.name)

        return None

    @property
    def most_recent_call(self):
        return self.call_set.order_by("-id").first()

    @property
    def most_recent_annotated_call(self):
        return self.annotated_calls[-1]  # TODO -- maybe inefficient?

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
    def annotated_calls(self):
        seat_cycle = libSeat.cycle()
        while True:
            s = next(seat_cycle)

            # The first call is made by dealer.
            if s.lho().value == self.board.dealer:
                break
        return zip(
            itertools.count(1),
            seat_cycle,
            # TODO -- might be nice to explicitly order these
            self.calls.all(),
        )

    @property
    def annotated_plays(self):
        seat_cycle = libSeat.cycle()
        while True:
            s = next(seat_cycle)

            # The first play is made by declarer.
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
        primary_key=True,
    )  # it's the default, but it can't hurt to be explicit.

    hand = models.ForeignKey(HandRecord, on_delete=models.CASCADE)
    # Now, the "what":
    # pass, bid, double, redouble

    serialized = models.CharField(  # type: ignore
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
        primary_key=True,
    )  # it's the default, but it can't hurt to be explicit.

    hand = models.ForeignKey(HandRecord, on_delete=models.CASCADE)

    serialized = models.CharField(  # type: ignore
        max_length=2,
        db_comment="A short string with which we can create a bridge.card.Card object",
    )

    def __str__(self):
        play = libCard.deserialize(self.serialized)
        return f"Mystery player at {self.hand.table} played {self.serialized} which means {play}"

    # TODO -- a constraint that says a given card must appear no more than once in a given handrecord


admin.site.register(Play)
