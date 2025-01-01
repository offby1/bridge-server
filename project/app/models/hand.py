from __future__ import annotations

import collections
import dataclasses
import logging
import time
from typing import TYPE_CHECKING, Any

import more_itertools
from bridge.auction import Auction as libAuction
from bridge.auction import AuctionException
from bridge.card import Card as libCard
from bridge.card import Suit as libSuit
from bridge.contract import Bid as libBid
from bridge.contract import Call as libCall
from bridge.contract import Contract as libContract
from bridge.seat import Seat as libSeat
from bridge.table import Hand as libHand
from bridge.table import Player as libPlayer
from bridge.table import Table as libTable
from bridge.xscript import HandTranscript
from django.contrib import admin
from django.core.cache import cache
from django.db import Error, models
from django.utils.functional import cached_property
from django_eventstream import send_event  # type: ignore [import-untyped]

from .player import Player
from .seat import Seat
from .utils import assert_type

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

    from django.db.models.manager import RelatedManager

    from . import Board, Player, Seat, Table  # noqa

logger = logging.getLogger(__name__)


class AuctionError(Exception):
    pass


class PlayError(Exception):
    pass


@dataclasses.dataclass
class TrickTuple:
    seat: libSeat
    card: libCard
    winner: bool


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
    send_event(channel=channel, event_type="message", data=data | {"time": time.time()})


class HandManager(models.Manager):
    def create(self, *args, **kwargs) -> Hand:
        from app.serializers import NewHandSerializer

        rv: Hand = super().create(*args, **kwargs)

        serialized_hand = NewHandSerializer(rv).data
        rv.send_event_to_players_and_hand(data={"new-hand": serialized_hand})
        logger.debug("Just created %s; dealer is %s", rv, rv.board.fancy_dealer)
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

    def players_current_seats(self):
        return Seat.objects.raw(
            """
        SELECT
            MAX(APP_SEAT.ID) AS ID
        FROM
            APP_SEAT
            JOIN PUBLIC.APP_PLAYER ON APP_PLAYER.ID = APP_SEAT.PLAYER_ID
        WHERE
            APP_PLAYER.ID IN (
                SELECT
                    APP_PLAYER.ID AS PLAYER_ID
                FROM
                    PUBLIC.APP_HAND
                    JOIN PUBLIC.APP_TABLE ON APP_TABLE.ID = APP_HAND.TABLE_ID
                    JOIN PUBLIC.APP_SEAT ON APP_SEAT.TABLE_ID = APP_TABLE.ID
                    JOIN PUBLIC.APP_PLAYER ON APP_PLAYER.ID = APP_SEAT.PLAYER_ID
                WHERE
                    APP_HAND.ID = %s
            )
        GROUP BY
            APP_SEAT.PLAYER_ID
        """,
            [self.pk],
        )

    @admin.display(boolean=True)
    @cached_property
    def is_abandoned(self) -> bool:
        if self.is_complete:
            return False
        if not all(s.player.currently_seated for s in self.table.seats):
            return True

        # Clearer, but less efficient
        # return any(s != s.player.current_seat for s in self.table.seats)

        return (
            self.table.seats.filter(pk__in={s.pk for s in self.players_current_seats()}).count() < 4
        )

    # At some point we will probably not bother sending to the "hand" channel, but for now ...
    def send_event_to_players_and_hand(self, *, data: dict[str, Any]) -> None:
        hand_channel = str(self.pk)
        player_channels = [f"system:player:{seat.player.pk}" for seat in self.table.seats]
        all_channels = [hand_channel, "all-tables", *player_channels]

        data = data.copy()
        data.setdefault("tempo_seconds", self.table.gimme_dat_fresh_tempo())
        data["serial_number"] = self.calls.count() + self.plays.count()
        data["hand_pk"] = self.pk
        for channel in all_channels:
            send_timestamped_event(channel=channel, data=data)

    def libraryThing(self, seat: Seat) -> libHand:
        from . import Seat

        assert_type(seat, Seat)
        cards = sorted(self.current_cards_by_seat()[seat.libraryThing])
        return libHand(cards=cards)

    # These attributes are set by view code.  The values come from method calls that take a Player as an argument; we do
    # this because it's not possible for the template to invoke a method that requires an argument.
    summary_for_this_viewer: str
    score_for_this_viewer: str | int

    @cached_property
    def libPlayers_by_seat(self) -> dict[libSeat, libPlayer]:
        rv: dict[libSeat, libPlayer] = {}
        seats = self.table.seats
        for direction_int in self.board.hand_strings_by_direction:
            lib_seat = libSeat(direction_int)
            seat = seats.filter(direction=direction_int).first()
            assert seat is not None
            name = seat.player_name
            rv[lib_seat] = libPlayer(seat=lib_seat, name=name)
        return rv

    @cached_property
    def lib_table_with_cards_as_dealt(self) -> libTable:
        players = list(self.libPlayers_by_seat.values())
        for p in players:
            assert_type(p, libPlayer)
        return libTable(players=players)

    def _cache_key(self) -> str:
        return self.pk

    @property
    def _cache_stats_keys(self) -> dict[str, str]:
        return {
            "hits": f"{self._cache_key()}_stats_hits",
            "misses": f"{self._cache_key()}_stats_misses",
        }

    def _cache_set(self, value: str) -> None:
        cache.set(self._cache_key(), value)

    def _cache_get(self) -> Any:
        return cache.get(self._cache_key())

    def _cache_log_stats(self) -> None:
        keys = self._cache_stats_keys
        logger.debug(f"{cache.get(keys['hits'])=} {cache.get(keys['misses'])=} ")

    def _cache_note_hit(self) -> None:
        key = self._cache_stats_keys["hits"]
        old = cache.get(key, default=0)
        cache.set(key, old + 1)

    def _cache_note_miss(self) -> None:
        key = self._cache_stats_keys["misses"]
        old = cache.get(key, default=0)
        cache.set(key, old + 1)
        self._cache_log_stats()

    def get_xscript(self) -> HandTranscript:
        def calls() -> Iterator[tuple[libPlayer, libCall]]:
            for seat, call in self.annotated_calls:
                player = self.libPlayers_by_seat[seat]
                yield (player, call.libraryThing)

        if (_xscript := self._cache_get()) is None:
            self._cache_note_miss()
            logger.debug(
                "Did not find xscript for hand %s; recreating it from %s calls and %s plays",
                self.pk,
                self.call_set.count(),
                self.play_set.count(),
            )
            lib_table = self.lib_table_with_cards_as_dealt
            auction = libAuction(table=lib_table, dealer=libSeat(self.board.dealer))
            dealt_cards_by_seat = {
                libSeat(direction): self.board.cards_for_direction(direction)
                for direction in (1, 2, 3, 4)
            }

            for player, call in calls():
                auction.append_located_call(player=player, call=call)

            _xscript = HandTranscript(
                table=lib_table,
                auction=auction,
                ns_vuln=self.board.ns_vulnerable,
                ew_vuln=self.board.ew_vulnerable,
                dealt_cards_by_seat=dealt_cards_by_seat,
            )

            for play in self.plays:
                _xscript.add_card(libCard.deserialize(play.serialized))

            self._cache_set(_xscript)
            logger.debug("Cached %s", _xscript)
        else:
            self._cache_note_hit()

        return _xscript

    def serializable_xscript(self) -> Any:
        return self.get_xscript().serializable()

    def add_call_from_player(self, *, player: libPlayer, call: libCall) -> None:
        assert_type(player, libPlayer)
        assert_type(call, libCall)

        if self.is_abandoned:
            msg = f"Hand {self} is abandoned"
            raise AuctionError(msg)

        auction = self.auction
        try:
            auction.raise_if_illegal_call(player=player, call=call)
        except AuctionException as e:
            raise AuctionError(str(e)) from e

        self.call_set.create(serialized=call.serialize())

        if self.declarer:  # the auction just settled
            contract = self.auction.status
            assert isinstance(contract, libContract)
            assert contract.declarer is not None
            self.send_event_to_players_and_hand(
                data={
                    "table": self.table.pk,
                    "contract_text": str(contract),
                    "contract": {
                        "opening_leader": contract.declarer.seat.lho().value,
                    },
                },
            )
        elif self.get_xscript().auction.status is libAuction.PassedOut:
            self.send_event_to_players_and_hand(
                data={
                    "table": self.table.pk,
                    "passed_out": "Yup, sure was",
                },
            )

    def add_play_from_player(self, *, player: libPlayer, card: libCard) -> Play:
        assert_type(player, libPlayer)
        assert_type(card, libCard)

        if self.is_abandoned:
            msg = f"Hand {self} is abandoned"
            raise PlayError(msg)

        legit_player = self.player_who_may_play
        if legit_player is None:
            msg = "For some crazy reason, nobody is allowed to play a card! Maybe the auction is incomplete, or the hand is over"
            raise PlayError(msg)

        if player.name != legit_player.name:
            msg = f"It is not {player.name}'s turn to play, but rather {legit_player.name}'s turn"
            raise PlayError(msg)

        remaining_cards = self.players_remaining_cards(player=player).cards
        if remaining_cards is None:
            msg = f"Cannot play a card from {libPlayer.name} because I don't know what cards they hold"
            raise PlayError(msg)

        legal_cards = self.get_xscript().legal_cards(some_cards=remaining_cards)
        if card not in legal_cards:
            msg = f"{self}, {self.board}: {card} is not a legal play for {player}; only {legal_cards} are"
            raise PlayError(msg)

        try:
            rv = self.play_set.create(hand=self, serialized=card.serialize())
        except Error as e:
            raise PlayError(str(e)) from e

        final_score = self.get_xscript().final_score()

        if final_score:
            self.send_event_to_players_and_hand(
                data={
                    "table": self.table.pk,
                    "final_score": str(final_score),
                },
            )

        return rv

    @property
    def auction(self) -> libAuction:
        return self.get_xscript().auction

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

        if self.is_abandoned:
            return None

        if self.auction.status is libAuction.Incomplete:
            libAllowed = self.auction.allowed_caller()
            return Player.objects.get_by_name(libAllowed.name)

        return None

    @property
    def player_who_may_play(self) -> Player | None:
        from . import Player

        if self.is_abandoned:
            return None

        if not self.auction.found_contract:
            return None

        seat_who_may_play = self.get_xscript().next_seat_to_play()
        pbs = self.libPlayers_by_seat
        return Player.objects.get_by_name(pbs[seat_who_may_play].name)

    def modPlayer_by_seat(self, seat: libSeat) -> Player:
        modelPlayer = self.players_by_direction[seat.value]
        return Player.objects.get_by_name(modelPlayer.name)

    @property
    def player_names(self) -> str:
        return ", ".join([p.name for p in self.players_by_direction.values()])

    @property
    def players_by_direction(self) -> dict[int, Player]:
        return {s.direction: s.player for s in self.table.seats}

    def current_cards_by_seat(self, *, as_dealt: bool = False) -> dict[libSeat, set[libCard]]:
        rv = {}
        for direction, cardstring in self.board.hand_strings_by_direction.items():
            seat = libSeat(direction)
            rv[seat] = {libCard.deserialize(c) for c in more_itertools.sliced(cardstring, 2)}

        if as_dealt:
            return rv

        if self.auction.found_contract:
            for tt in self.annotated_plays:
                rv[tt.seat].remove(tt.card)

        return rv

    def players_remaining_cards(self, *, player: libPlayer) -> libHand:
        ccbs = self.current_cards_by_seat()
        return libHand(cards=list(ccbs[player.seat]))

    def display_skeleton(self, *, as_dealt: bool = False) -> DisplaySkeleton:
        """A simplified representation of the hand, with all the attributes "filled in" -- about halfway between the model and the view."""
        xscript = self.get_xscript()
        whose_turn_is_it = None

        if xscript.auction.found_contract:
            whose_turn_is_it = xscript.next_seat_to_play()

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
                        c in xscript.legal_cards(some_cards=list(cards))
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

    @cached_property
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

    @cached_property
    def is_complete(self):
        x = self.get_xscript()
        return x.num_plays == 52 or x.auction.status is libAuction.PassedOut

    def serialized_plays(self):
        return [p.serialized for p in self.play_set.order_by("id")]

    @property
    def calls(self):
        """All the calls in this hand, in chronological order.

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

    @property
    def annotated_calls(self) -> Iterable[tuple[libSeat, Call]]:
        return list(
            zip(
                self._seat_cycle_starting_with_dealer,
                self.calls.all(),
            ),
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
                flattened.append(TrickTuple(seat=p.seat, card=p.card, winner=p.wins_the_trick))

        return flattened

    def trick_counts_by_direction(self) -> dict[str, int]:
        return {
            "N/S" if north_or_east == 1 else "E/W": count
            for north_or_east, count in collections.Counter(
                p.seat.value % 2 for p in self.annotated_plays if p.winner
            ).items()
        }

    # This is meant for use by get_xscript; anyone else who wants to examine our plays should call that.
    @property
    def plays(self):
        return self.play_set.order_by("id")

    def toggle_open_access(self) -> None:
        if self.is_abandoned:
            return

        self.open_access = not self.open_access
        self.save()
        self.send_event_to_players_and_hand(data={"open-access-status": self.open_access})

    def summary_as_viewed_by(self, *, as_viewed_by: Player | None) -> tuple[str, str | int]:
        if as_viewed_by is None:
            return "Remind me -- who are you, again?", "-"

        if (
            self.board.what_can_they_see(player=as_viewed_by)
            != self.board.PlayerVisibility.everything
            and as_viewed_by.name not in self.player_names
        ):
            return (
                f"Sorry, {as_viewed_by}, but you have not completely played board {self.board.short_string()}, so later d00d",
                "-",
            )

        auction_status = self.get_xscript().auction.status

        if auction_status is self.auction.Incomplete:
            return "Auction incomplete", "-"

        if auction_status is self.auction.PassedOut:
            return "Passed Out", 0

        total_score: int | str

        my_seat = None
        my_hand_for_this_board = as_viewed_by.hand_at_which_board_was_played(self.board)
        if my_hand_for_this_board is not None:
            my_seat = my_hand_for_this_board.table.seats.filter(player=as_viewed_by).first()
        fs = self.get_xscript().final_score()

        if fs is None or my_seat is None:
            total_score = "-"
            trick_summary = "still being played"
        else:
            my_seat_direction = my_seat.direction
            if my_seat_direction in {1, 3}:  # north/south
                total_score = fs.north_south_points or -fs.east_west_points
            else:
                total_score = fs.east_west_points or -fs.north_south_points
            trick_summary = fs.trick_summary

        return (f"{auction_status}: {trick_summary}", total_score)

    def __str__(self) -> str:
        return f"Hand {self.pk}: {self.calls.count()} calls; {self.plays.count()} plays"


@admin.register(Hand)
class HandAdmin(admin.ModelAdmin):
    list_display = ["table", "board", "open_access", "is_abandoned"]
    list_filter = ["open_access"]


class CallManager(models.Manager):
    def create(self, *args, **kwargs) -> Call:
        from app.serializers import ReadOnlyCallSerializer

        if "hand_id" in kwargs:
            h = Hand.objects.get(pk=kwargs["hand_id"])
        elif "hand" in kwargs:
            h = kwargs["hand"]
        else:
            msg = f"wtf: {kwargs=}"
            raise Exception(msg)

        x = h.get_xscript()

        rv = super().create(*args, **kwargs)

        c = libBid.deserialize(kwargs["serialized"])

        x.add_call(c)
        rv.hand._cache_set(x)

        rv.hand.send_event_to_players_and_hand(
            data={"new-call": ReadOnlyCallSerializer(rv).data},
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
    def seat_pk(self) -> int | None:
        for pc in self.hand.get_xscript().auction.player_calls:
            if pc.call.serialize() == self.serialized:
                return self.hand.table.seats.get(direction=pc.player.seat.value).pk

        return None

    @property
    def libraryThing(self):
        return libBid.deserialize(self.serialized)

    def __str__(self) -> str:
        return str(self.libraryThing)


admin.site.register(Call)


class PlayManager(models.Manager):
    def create(self, *args, **kwargs) -> Play:
        """Only Hand.add_play_from_player may call me; the rest of y'all should call *that*."""
        from app.serializers import ReadOnlyPlaySerializer

        # Apparently I call this both ways :shrug:
        if "hand_id" in kwargs:
            h = Hand.objects.get(pk=kwargs["hand_id"])
        elif "hand" in kwargs:
            h = kwargs["hand"]
        else:
            msg = f"wtf: {kwargs=}"
            raise Exception(msg)

        x = h.get_xscript()

        rv = super().create(*args, **kwargs)

        # See corresponding TODO in CallManager
        x.add_card(libCard.deserialize(kwargs["serialized"]))
        rv.hand._cache_set(x)

        rv.hand.send_event_to_players_and_hand(
            data={"new-play": ReadOnlyPlaySerializer(rv).data},
        )

        return rv


class Play(models.Model):
    id = models.BigAutoField(
        primary_key=True,
    )  # it's the default, but it can't hurt to be explicit.

    hand = models.ForeignKey["Hand"](Hand, on_delete=models.CASCADE)

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

    @property
    def seat_pk(self) -> int | None:
        for t in self.hand.get_xscript().tricks:
            for p in t.plays:
                if p.card.serialize() == self.serialized:
                    return self.hand.table.seats.get(direction=p.seat.value).pk
        return None

    @cached_property
    def seat(self) -> libSeat:
        for tt in self.hand.annotated_plays:
            if self.serialized == tt.card.serialize():
                return tt.seat

        msg = f"Internal error, cannot find {self.serialized} in {[p.card for p in self.hand.annotated_plays]}"
        raise Exception(msg)


admin.site.register(Play)
