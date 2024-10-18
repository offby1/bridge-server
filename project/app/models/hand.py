from __future__ import annotations

import collections
import dataclasses
import logging
import time
from typing import TYPE_CHECKING, Any, Iterable, Iterator

import more_itertools
from bridge.auction import Auction as libAuction
from bridge.card import Card as libCard
from bridge.card import Suit as libSuit
from bridge.contract import Bid as libBid
from bridge.contract import Call as libCall
from bridge.contract import Contract as libContract
from bridge.seat import Seat as libSeat
from bridge.table import Hand as libHand
from bridge.table import Player as libPlayer
from bridge.xscript import HandTranscript
from django.contrib import admin
from django.db import models
from django.utils.functional import cached_property
from django_eventstream import send_event  # type: ignore

from .player import Player
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


@dataclasses.dataclass
class SuitHolding:
    """Given the state of the play, can one of these cards be played?  "Yes" if the xscript says we're the current
    player, and if all the cards_by_suit are "legal_cards" according to the xscript.

    Note that either all our cards are legal_cards, or none are.

    """

    legal_now: bool

    cards_of_one_suit: list[libCard]


@dataclasses.dataclass
class AllFourSuitHoldings:
    spades: SuitHolding
    hearts: SuitHolding
    diamonds: SuitHolding
    clubs: SuitHolding

    """The textual summary is redundant, in that it summarizes what's present in the four SuitHoldings.  It's for when
    the view is displaying an opponent's hand -- obviously the player doesn't get to see the cards; instead they see a
    message like "12 cards".

    """

    textual_summary: str

    @property
    def this_hands_turn_to_play(self) -> bool:
        for suit_name in ("spades", "hearts", "clubs", "diamonds"):
            holding = getattr(self, suit_name)

            if holding.legal_now:
                return True
        return False

    def from_suit(self, s: libSuit) -> SuitHolding:
        return getattr(self, s.name().lower())

    def items(self) -> Iterable[tuple[libSuit, SuitHolding]]:
        for suitname, suit_value in libSuit.__members__.items():
            holding = getattr(self, suitname.lower())
            yield (suit_value, holding)


@dataclasses.dataclass
class DisplaySkeleton:
    holdings_by_seat: dict[libSeat, AllFourSuitHoldings]

    def items(self) -> Iterable[tuple[libSeat, AllFourSuitHoldings]]:
        return self.holdings_by_seat.items()

    def __getitem__(self, seat: libSeat) -> AllFourSuitHoldings:
        assert_type(seat, libSeat)
        return self.holdings_by_seat[seat]


def send_timestamped_event(*, channel: str, data: dict[str, Any]) -> None:
    for ch in (channel, "all-tables"):
        send_event(channel=ch, event_type="message", data=data | {"time": time.time()})


class HandManager(models.Manager):
    def create(self, *args, **kwargs) -> Hand:
        from app.serializers import NewHandSerializer

        rv = super().create(*args, **kwargs)

        send_timestamped_event(
            channel=str(rv.table.pk), data={"new-hand": NewHandSerializer(rv).data}
        )

        return rv


class Hand(models.Model):
    """All the calls and plays for a given hand."""

    if TYPE_CHECKING:
        call_set = RelatedManager["Call"]()
        play_set = RelatedManager["Play"]()

    objects = HandManager()

    # The "when", and, when combined with knowledge of who dealt, the "who"
    id = models.BigAutoField(
        primary_key=True,
    )  # it's the default, but it can't hurt to be explicit.

    # The "where"
    table = models.ForeignKey["Table"]("Table", on_delete=models.CASCADE)

    # The "what" is in our implicit "call_set" and "play_set" attributes, along with this board.

    board = models.ForeignKey["Board"]("Board", on_delete=models.CASCADE)

    open_access = models.BooleanField(
        default=False,
        db_comment='For debugging only! Settable via the admin site, and maaaaybe by a special "god-mode" switch in the UI',
    )  # type: ignore

    def libraryThing(self, seat: Seat) -> libHand:
        from . import Seat

        assert_type(seat, Seat)
        return libHand(cards=sorted(self.current_cards_by_seat()[seat.libraryThing]))

    summary_for_this_viewer: str

    _xscript: HandTranscript

    def get_xscript(self) -> HandTranscript:
        if not hasattr(self, "_xscript"):
            self._xscript = HandTranscript(
                table=self.table.libraryThing,
                auction=self.auction,
                ns_vuln=self.board.ns_vulnerable,
                ew_vuln=self.board.ew_vulnerable,
            )

        num_missing_plays = self.plays.count() - self._xscript.num_plays
        if num_missing_plays > 0:
            p: Play
            for p in reversed(self.plays.order_by("-id").all()[0:num_missing_plays]):
                self._xscript.add_card(libCard.deserialize(p.serialized))

        return self._xscript

    def add_call_from_player(self, *, player: libPlayer, call: libCall):
        assert_type(player, libPlayer)
        assert_type(call, libCall)

        auction = self.auction
        try:
            auction.raise_if_illegal_call(player=player, call=call)
        except Exception as e:
            raise AuctionError(str(e)) from e

        self.call_set.create(serialized=call.serialize())

        if self.declarer:  # the auction just settled
            contract = self.auction.status
            assert isinstance(contract, libContract)
            assert contract.declarer is not None
            send_timestamped_event(
                channel=str(self.pk),
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
        legal_cards = self.get_xscript().legal_cards(
            some_hand=self.players_remaining_cards(player=player)
        )
        if card not in legal_cards:
            msg = f"{card} is not a legal play"
            raise PlayError(msg)

        rv = self.play_set.create(hand=self, serialized=card.serialize())

        self._xscript.add_card(card)

        final_score = self.get_xscript().final_score()

        if final_score:
            send_timestamped_event(
                channel=str(self.pk),
                data={
                    "table": self.table.pk,
                    "final_score": str(final_score),
                },
            )

        return rv

    @cached_property
    def auction(self) -> libAuction:
        dealer = libSeat(self.board.dealer)

        libTable = self.table.libraryThing
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

        libPlayer = self.get_xscript().named_seats[0]

        return Player.objects.get_by_name(libPlayer.name)

    def modPlayer_by_seat(self, seat: libSeat) -> Player:
        modelPlayer = self.players_by_direction[seat.value]
        return Player.objects.get_by_name(modelPlayer.name)

    @property
    def player_names(self) -> str:
        return ", ".join([p.name for p in self.players_by_direction.values()])

    def player_can_examine(self, player: Player) -> bool:
        return player.has_ever_seen_board(self.board)

    @property
    def players_by_direction(self) -> dict[int, Player]:
        return {s.direction: s.player for s in self.table.seats}

    # TODO -- this duplicates players_remaining_cards
    def current_cards_by_seat(self, *, as_dealt: bool = False) -> dict[libSeat, set[libCard]]:
        rv = {}
        for direction, cardstring in self.board.hand_strings_by_direction.items():
            seat = libSeat(direction)
            rv[seat] = {libCard.deserialize(c) for c in more_itertools.sliced(cardstring, 2)}

        if as_dealt:
            return rv

        if self.auction.found_contract:
            for _index, libseat, libcard, _is_winner in self.annotated_plays:
                rv[libseat].remove(libcard)

        return rv

    # TODO -- this duplicates current_cards_by_seat
    def players_remaining_cards(self, *, player: libPlayer) -> libHand:
        dealt_cards = set(player.hand.cards)
        played_cards = {
            libCard.deserialize(p.serialized) for p in self.play_set.all()
        }  # this includes the other three player's plays, too, but it doesn't matter!
        current_cards = dealt_cards - played_cards
        return libHand(cards=list(current_cards))

    def display_skeleton(self, *, as_dealt: bool = False) -> DisplaySkeleton:
        """
        A simplified representation of the hand, with all the attributes "filled in" -- about halfway between the model and the view.
        """
        xscript = self.get_xscript()
        whose_turn_is_it = None

        if xscript.auction.found_contract:
            whose_turn_is_it = xscript.next_seat()

        rv = {}
        # xscript.legal_cards tells us which cards are legal for the current player.
        for seat, cards in self.current_cards_by_seat(as_dealt=as_dealt).items():
            assert_type(seat, libSeat)

            cards_by_suit = collections.defaultdict(list)
            for c in cards:
                cards_by_suit[c.suit].append(c)

            kwargs = {}

            for suit in libSuit:
                legal_now = False
                if seat == whose_turn_is_it:
                    legal_now = any(
                        c in xscript.legal_cards(some_hand=libHand(cards=sorted(cards)))
                        for c in cards_by_suit[suit]
                    )

                kwargs[suit.name().lower()] = SuitHolding(
                    cards_of_one_suit=cards_by_suit[suit],
                    legal_now=legal_now,
                )

            rv[seat] = AllFourSuitHoldings(
                **kwargs,
                textual_summary=f"{len(cards)} cards",
            )
        return DisplaySkeleton(holdings_by_seat=rv)

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

    def serialized_calls(self):
        return [c.serialized for c in self.call_set.order_by("id")]

    @property
    def is_complete(self):
        return len(self.serialized_plays()) == 52

    def serialized_plays(self):
        return [p.serialized for p in self.play_set.order_by("id")]

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

        for t in self.get_xscript().tricks:
            # Who won this trick?
            for p in t.plays:
                flattened.append((1 + len(flattened), p.seat, p.card, p.wins_the_trick))

        return flattened

    @property
    def status(self) -> str:
        winning_plays = self.play_set.filter(won_its_trick=True)
        wins_by_seat: dict[libSeat, int] = collections.defaultdict(int)
        for p in winning_plays:
            wins_by_seat[p.seat] += 1
        east_west = wins_by_seat[libSeat.EAST] + wins_by_seat[libSeat.WEST]
        north_south = wins_by_seat[libSeat.NORTH] + wins_by_seat[libSeat.SOUTH]

        return f"{east_west=}; {north_south=}"

    @property
    def plays(self):
        return self.play_set.order_by("id")

    def toggle_open_access(self) -> None:
        self.open_access = not self.open_access
        self.save()
        send_timestamped_event(channel=str(self.pk), data={"open-access-status": self.open_access})

    def summary_as_viewed_by(self, *, as_viewed_by: Player | None) -> str:
        if as_viewed_by is None:
            return "Remind me -- who are you, again?"

        if not as_viewed_by.has_ever_seen_board(self.board):
            return f"Sorry, {as_viewed_by}, but you have never played {self.board}, so later d00d"

        if not self.is_complete:
            if self.get_xscript().auction.status == self.get_xscript().auction.Incomplete:
                censored_auction_summary = "is incomplete"
            elif self.get_xscript().auction.status == self.get_xscript().auction.PassedOut:
                censored_auction_summary = "was passed out"
            else:
                censored_auction_summary = "is complete"

            censored_play_summary = f"{len(self.plays)} cards played"
            return f"Auction {censored_auction_summary}; {censored_play_summary}"

        fs = self.get_xscript().final_score()
        assert fs is not None
        return f"{fs.trick_summary}"

    def __str__(self):
        return f"Hand {self.pk}: {self.calls.count()} calls; {self.plays.count()} plays"


admin.site.register(Hand)


class CallManager(models.Manager):
    def create(self, *args, **kwargs) -> Hand:
        from app.serializers import CallSerializer

        rv = super().create(*args, **kwargs)

        send_timestamped_event(
            channel=str(rv.hand.pk),
            data={"new-call": CallSerializer(rv).data},
        )

        return rv


class Call(models.Model):
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

    objects = CallManager()

    @property
    def libraryThing(self):
        return libBid.deserialize(self.serialized)

    def __str__(self):
        return str(self.libraryThing)


admin.site.register(Call)


class PlayManager(models.Manager):
    def create(self, *args, **kwargs) -> Hand:
        """
        Only Hand.add_play_from_player may call me; the rest of y'all should call *that*.
        """
        from app.serializers import PlaySerializer

        rv = super().create(*args, **kwargs)

        send_timestamped_event(
            channel=str(rv.hand.pk),
            data={"new-play": PlaySerializer(rv).data},
        )

        return rv


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

    objects = PlayManager()

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


admin.site.register(Play)
