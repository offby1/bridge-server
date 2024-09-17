from __future__ import annotations

import collections
import itertools
from typing import TYPE_CHECKING, Iterator

import more_itertools
from bridge.auction import Auction as libAuction
from bridge.card import Card as libCard
from bridge.contract import Bid as libBid
from bridge.contract import Call as libCall
from bridge.contract import Contract as libContract
from bridge.seat import Seat as libSeat
from bridge.table import Player as libPlayer
from bridge.xscript import HandTranscript
from django.contrib import admin
from django.db import models
from django.utils.functional import cached_property
from django_eventstream import send_event  # type: ignore

from .utils import assert_type

if TYPE_CHECKING:
    from django.db.models.manager import RelatedManager

    from . import Board, Player, Seat, Table  # noqa


class AuctionException(Exception):
    pass


class PlayException(Exception):
    pass


TrickTuple = tuple[int, libSeat, libCard, bool]
TrickTuples = list[TrickTuple]


class HandAction(models.Model):
    """
    All the calls and plays for a given hand.
    """

    if TYPE_CHECKING:
        call_set = RelatedManager["Call"]()
        play_set = RelatedManager["Play"]()

    # The "when", and, when combined with knowledge of who dealt, the "who"
    id = models.BigAutoField(
        primary_key=True,
    )  # it's the default, but it can't hurt to be explicit.

    # The "where"
    table = models.ForeignKey["Table"]("Table", on_delete=models.CASCADE)

    # The "what" is in our implicit "call_set" and "play_set" attributes, along with this board.
    board = models.OneToOneField["Board"]("Board", on_delete=models.CASCADE)

    @property
    def xscript(self) -> HandTranscript:
        rv = HandTranscript(
            table=self.table.libraryThing(),
            auction=self.table.current_auction,
        )
        # *sigh* now replay the entire hand
        play_pks_by_card_played = {}
        for _index, p in enumerate(self.plays):
            play_pks_by_card_played[p.serialized] = p.pk
            rv.add_card(libCard.deserialize(p.serialized))

        if rv.tricks:
            last_trick = rv.tricks[-1]
            if last_trick.is_complete():
                winning_play = [p for p in last_trick if p.wins_the_trick]
                assert len(winning_play) == 1
                winning_card_str = winning_play[0].card.serialize()
                winning_play_pk = play_pks_by_card_played[winning_card_str]
                # TODO -- I think this gets called 3 or 4 times, all but the first call are redundant.
                self.play_set.filter(pk=winning_play_pk).update(won_its_trick=True)

        return rv

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

            if self.declarer:  # the auction just settled
                contract = self.auction.status
                assert isinstance(contract, libContract)
                send_event(
                    channel=channel,
                    event_type="message",
                    data={
                        "table": self.table.pk,
                        "contract_text": str(contract),
                        "contract": {
                            "opening_leader": contract.declarer.seat.lho().value,
                        },
                    },
                )

    def add_play_from_player(self, *, player: libPlayer, card: libCard) -> Play:
        assert_type(player, libPlayer)
        assert_type(card, libCard)

        legit_player = self.player_who_may_play
        if legit_player is None:
            msg = "For some crazy reason, nobody is allowed to play a card! Maybe the auction is incomplete, or the hand is over"
            raise PlayException(msg)

        if player.name != legit_player.name:
            msg = f"It is not {player.name}'s turn to play"
            raise PlayException(msg)

        legal_cards = self.xscript.legal_cards()
        if card not in legal_cards:
            msg = f"{card} is not a legal play"
            raise PlayException(msg)

        # If this is the last play in a trick, go back and update the play that won it.
        rv = self.play_set.create(serialized=card.serialize())

        from app.models import Player

        modelPlayer = Player.objects.get_by_name(player.name)
        # TODO -- this duplicates the (admittedly trivial) `_auction_channel_for_table` in views.table
        for channel in (str(self.table.pk), "all-tables"):
            send_event(
                channel=channel,
                event_type="message",
                data={"table": self.table.pk, "player": modelPlayer.pk, "card": card.serialize()},
            )

        return rv

    @property
    def auction(self) -> libAuction:
        dealer = libSeat(self.board.dealer)

        libTable = self.table.libraryThing()
        rv = libAuction(table=libTable, dealer=dealer)
        for _index, seat, call in self.annotated_calls:
            player = libTable.players[seat]
            rv.append_located_call(player=player, call=call.libraryThing)
        return rv

    @property
    def declarer(self) -> libPlayer | None:
        if not self.auction.found_contract:
            return None
        return self.auction.declarer

    @property
    def dummy(self) -> libPlayer | None:
        if not self.auction.found_contract:
            return None
        return self.auction.dummy

    @property
    def player_who_may_call(self) -> Player | None:
        from . import Player

        if self.auction.status is libAuction.Incomplete:
            libAllowed = self.auction.allowed_caller()
            return Player.objects.get_by_name(libAllowed.name)

        return None

    @property
    def player_who_may_play(self) -> Player | None:
        from . import Player

        if not self.auction.found_contract:
            return None

        libPlayer = self.xscript.players[0]

        return Player.objects.get_by_name(libPlayer.name)

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
    def tricks(self) -> Iterator[TrickTuples]:
        return more_itertools.chunked(self.annotated_plays, 4)

    @property
    def current_trick(self) -> TrickTuples | None:
        tricks = list(self.tricks)
        if not tricks:
            return None

        return tricks[-1]

    @property
    def annotated_plays(self) -> TrickTuples:
        flattened: TrickTuples = []

        for t in self.xscript.tricks:
            # Who won this trick?
            for p in t.plays:
                flattened.append((1 + len(flattened), p.player.seat, p.card, p.wins_the_trick))

        return flattened

    @property
    def status(self):
        winning_plays = self.play_set.filter(won_its_trick=True)
        wins_by_seat = collections.defaultdict(int)
        for p in winning_plays:
            wins_by_seat[p.seat] += 1
        east_west = wins_by_seat[libSeat.EAST] + wins_by_seat[libSeat.WEST]
        north_south = wins_by_seat[libSeat.NORTH] + wins_by_seat[libSeat.SOUTH]

        return f"{east_west=}; {north_south=}"

    @property
    def plays(self):
        return self.play_set.order_by("id")

    def __str__(self):
        return f"Auction: {';'.join([str(c) for c in self.calls])}\nPlay: {';'.join([str(p) for p in self.plays])}"


admin.site.register(HandAction)


class Call(models.Model):
    id = models.BigAutoField(
        primary_key=True,
    )  # it's the default, but it can't hurt to be explicit.

    hand = models.ForeignKey(HandAction, on_delete=models.CASCADE)
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

    # This is redundant -- it can in theory be computed given that we know who made the opening lead, the trump suit,
    # and the rules of bridge.  But geez.
    won_its_trick = models.BooleanField(null=True)

    hand = models.ForeignKey(HandAction, on_delete=models.CASCADE)

    serialized = models.CharField(  # type: ignore
        max_length=2,
        db_comment="A short string with which we can create a bridge.card.Card object",
    )

    @cached_property
    def seat(self) -> libSeat:
        for _index, seat, candidate, _is_winner in self.hand.annotated_plays:
            if self.serialized == candidate.serialize():
                return seat

        msg = f"Internal error, cannot find {self.serialized} in {[p[2] for p in self.hand.annotated_plays]}"
        raise Exception(msg)

    def __str__(self) -> str:
        star = ""
        if self.won_its_trick:
            star = "*"
        return f"{self.seat} at {self.hand.table} played {self.serialized}{star}"

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["hand", "serialized"],
                name="%(app_label)s_%(class)s_a_card_can_be_played_only_once",
            ),
        ]


admin.site.register(Play)