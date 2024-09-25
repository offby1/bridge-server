from __future__ import annotations

import collections
import logging
from typing import TYPE_CHECKING, Iterable, Iterator

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

logger = logging.getLogger(__name__)


class AuctionError(Exception):
    pass


class PlayError(Exception):
    pass


TrickTuple = tuple[int, libSeat, libCard, bool]
TrickTuples = list[TrickTuple]


class Hand(models.Model):
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
                # TODO: I am not setting any of these to False.  I could probably set all the plays to the correct
                # value, with a single query, by using a Django ORM annotation.
                self.play_set.filter(pk=winning_play_pk).update(won_its_trick=True)

        return rv

    def add_call_from_player(self, *, player: libPlayer, call: libCall):
        assert_type(player, libPlayer)
        assert_type(call, libCall)

        auction = self.auction
        try:
            auction.raise_if_illegal_call(player=player, call=call)
        except Exception as e:
            raise AuctionError(str(e)) from e

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
                assert contract.declarer is not None
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
            raise PlayError(msg)

        if player.name != legit_player.name:
            msg = f"It is not {player.name}'s turn to play"
            raise PlayError(msg)

        # If this is the last play in a trick, `xscript` will silently go back and update the play that won it.
        legal_cards = self.xscript.legal_cards()
        if card not in legal_cards:
            msg = f"{card} is not a legal play"
            raise PlayError(msg)

        rv = self.play_set.create(serialized=card.serialize())

        if final_score := self.xscript.final_score(
            declarer_vulnerable=True  # TODO -- this is a lie half the time
        ):
            kwargs = {
                "channel": str(self.table.pk),
                "event_type": "message",
                "data": {
                    "table": self.table.pk,
                    "final_score": str(final_score),
                },
            }
            logger.debug(f"Sending event {kwargs=}")
            send_event(**kwargs)

        from app.models import Player

        modelPlayer = Player.objects.get_by_name(player.name)
        # TODO -- this duplicates the (admittedly trivial) `_auction_channel_for_table` in views.table
        for channel in (str(self.table.pk), "all-tables"):
            send_event(
                channel=channel,
                event_type="message",
                data={
                    "table": self.table.pk,
                    "player": modelPlayer.pk,
                    "card": card.serialize(),
                    "play_id": rv.pk,
                },
            )

        return rv

    @property
    def auction(self) -> libAuction:
        dealer = libSeat(self.board.dealer)

        libTable = self.table.libraryThing()
        rv = libAuction(table=libTable, dealer=dealer)
        for seat, call in self.annotated_calls:
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
        """
        All the calls in this hand, in chronological order.
        `call_set` probably does the same thing; I'm just not yet certain of the default ordering.
        """
        return self.call_set.order_by("id")

    @property
    def _seat_cycle_starting_with_dealer(self):
        seat_cycle = libSeat.cycle()
        while True:
            s = next(seat_cycle)

            # The first call is made by dealer.
            if s.lho().value == self.board.dealer:
                return seat_cycle

    @cached_property
    def annotated_calls(self) -> Iterable[tuple[libSeat, Call]]:
        return list(
            zip(
                self._seat_cycle_starting_with_dealer,
                self.calls.all(),
            )
        )

    @property
    def last_annotated_call(self) -> tuple[libSeat, Call]:
        seat = self.call_set.order_by("-id").first()
        assert seat is not None
        return (next(self._seat_cycle_starting_with_dealer), seat)

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
        return f"Auction: {self.calls.count()} calls; Play: {self.plays.count()} plays"


admin.site.register(Hand)


# This simple mechanism might be a better way to send events -- I can rig this up for every model I care about (calls and plays in particular), and this might be cleaner than doing it however I'm currently doing it.


# Note that if you create one of these like this
# c = Call(hand=Hand.objects.first(), serialized="1N")
# c.save()
# then this magic will *not* trigger.  I'm not in the habit of creating objects that way, but it's a potential gotcha.
class CallManager(models.Manager):
    def create(self, *args, **kwargs):
        _serialized, _hand = kwargs["serialized"], kwargs["hand"]
        return super().create(*args, **kwargs)


class Call(models.Model):
    objects = CallManager()

    id = models.BigAutoField(
        primary_key=True,
    )  # it's the default, but it can't hurt to be explicit.

    hand = models.ForeignKey(Hand, on_delete=models.CASCADE)
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

    hand = models.ForeignKey(Hand, on_delete=models.CASCADE)

    serialized = models.CharField(  # type: ignore
        max_length=2,
        db_comment="A short string with which we can create a bridge.card.Card object",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["hand", "serialized"],
                name="%(app_label)s_%(class)s_a_card_can_be_played_only_once",
            ),
        ]

    @cached_property
    def seat(self) -> libSeat:
        for _index, seat, candidate, _is_winner in self.hand.annotated_plays:
            if self.serialized == candidate.serialize():
                return seat

        msg = f"Internal error, cannot find {self.serialized} in {[p[2] for p in self.hand.annotated_plays]}"
        raise Exception(msg)

    @cached_property
    def str(self) -> str:
        star = ""
        if self.won_its_trick:
            star = "*"
        return f"{self.seat} at {self.hand.table} played {self.serialized}{star}"


admin.site.register(Play)
