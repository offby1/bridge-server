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
from bridge.xscript import CBS, HandTranscript
from django.contrib import admin
from django.core.cache import cache
from django.db import Error, models
from django.utils.functional import cached_property
from django_eventstream import send_event  # type: ignore [import-untyped]

from . import Board
from .player import Player
from .seat import Seat
from .tournament import Tournament
from .types import PK, PK_from_str
from .utils import assert_type

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

    from django.db.models.manager import RelatedManager

    from . import Table

logger = logging.getLogger(__name__)


class AuctionError(Exception):
    pass


class HandError(Exception):
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


def send_timestamped_event(
    *, channel: str, data: dict[str, Any], when: float | None = None
) -> None:
    if when is None:
        when = time.time()
    send_event(channel=channel, event_type="message", data=data | {"time": when})


class HandManager(models.Manager):
    def create(self, *args, **kwargs) -> Hand:
        board = kwargs.get("board")
        assert board is not None
        table = kwargs.get("table")
        assert table is not None

        assert (
            board.tournament == table.tournament
        ), f"Nuts, {board.tournament=} != {table.tournament=}"

        seats = table.seat_set
        player_pks = seats.values_list("player__id", flat=True)
        players_qs = Player.objects.filter(pk__in=player_pks)

        expression = models.Q(pk__in=[])
        for p in players_qs:
            expression |= models.Q(pk__in=p.boards_played.all())

        if Board.objects.filter(expression).filter(pk=board.pk).exists():
            players = Player.objects.filter(pk__in=player_pks)
            msg = f"Cannot seat all of {[p.name for p in players]} because at least one them has already played {board}"
            raise HandError(msg)

        for p in players_qs:
            p.taint_board(board_pk=board.pk)
            p.save()

        logger.debug(
            "New hand: board #%s at table %s with %s",
            board.display_number,
            table.pk,
            [p.name for p in players_qs],
        )

        return super().create(*args, **kwargs)


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

    abandoned_because = models.CharField(max_length=100, null=True)

    def _check_for_expired_tournament(self) -> None:
        tour = self.table.tournament
        if tour.play_completion_deadline_has_passed():
            deadline = tour.play_completion_deadline
            assert deadline is not None

            tour.is_complete = True
            tour.save()

            from .table import TableException

            msg = f"Tournament #{tour.display_number}'s play completion deadline ({deadline.isoformat()}) has passed!"
            raise TableException(msg)

    @property
    def event_channel_name(self):
        return f"hand:{self.pk}"

    @staticmethod
    def hand_pk_from_event_channel_name(cn: str) -> PK | None:
        pieces = cn.split("hand:")
        if len(pieces) != 2:
            return None
        return PK_from_str(pieces[1])

    def players(self) -> models.QuerySet:
        return Player.objects.filter(pk__in=self.table.seats.values_list("player", flat=True))

    # TODO -- maybe https://www.better-simple.com/django/2025/01/01/complex-django-filters-with-subquery/ has some hints
    # for orm-ifying this
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

    @cached_property
    @admin.display
    def is_abandoned(self) -> bool:
        if self.is_complete:
            return False

        if self.abandoned_because is not None:
            return True

        players = [s.player for s in self.table.seats]
        unseated_players = [p for p in players if not p.currently_seated]

        if unseated_players:
            self.abandoned_because = (
                f"{[p.name for p in unseated_players]} left their seats for the lobby"
            )
            return True

        player_table_tuples = [
            (s.player.name, s.table.pk)
            for s in self.players_current_seats()
            if s.table.pk != self.table.pk
        ]
        if not player_table_tuples:
            return False
        self.abandoned_because = f"Some players are now at other tables: {player_table_tuples}"
        return True

    def send_event_to_players_and_hand(self, *, data: dict[str, Any]) -> None:
        hand_channel = self.event_channel_name
        player_channels = [s.player.event_channel_name for s in self.table.seats]
        all_channels = [hand_channel, "all-tables", *player_channels]

        data = data.copy()
        data["tempo_seconds"] = self.table.tempo_seconds
        data["hand_pk"] = self.pk
        now = time.time()
        for channel in all_channels:
            send_timestamped_event(channel=channel, data=data, when=now)

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
            assert seat is not None, f"Alas! No seat {direction_int=} at {self}"
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

    @staticmethod
    def _cache_stats_keys() -> dict[str, str]:
        return {
            "hits": "cache_stats_hits",
            "misses": "cache_stats_misses",
        }

    @staticmethod
    def _cache_stats() -> dict[str, int]:
        return {k: cache.get(k) for k in ("hits", "misses")}

    def _cache_set(self, value: str) -> None:
        cache.set(self._cache_key(), value)

    def _cache_get(self) -> Any:
        return cache.get(self._cache_key())

    def _cache_note_hit(self) -> None:
        key = "hits"
        old = cache.get(key, default=0)
        cache.set(key, old + 1)

    def _cache_note_miss(self) -> None:
        key = "misses"
        old = cache.get(key, default=0)
        cache.set(key, old + 1)

    def get_xscript(self) -> HandTranscript:
        def calls() -> Iterator[tuple[libPlayer, libCall]]:
            for seat, call in self.annotated_calls:
                player = self.libPlayers_by_seat[seat]
                yield (player, call.libraryThing)

        if (_xscript := self._cache_get()) is None:
            self._cache_note_miss()

            lib_table = self.lib_table_with_cards_as_dealt
            auction = libAuction(table=lib_table, dealer=libSeat(self.board.dealer))
            dealt_cards_by_seat: CBS = {
                libSeat(direction): self.board.cards_for_direction(direction)
                for direction in "NESW"
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
        else:
            self._cache_note_hit()

        return _xscript

    def serializable_xscript(self) -> Any:
        return self.get_xscript().serializable()

    def add_call_from_player(self, *, player: libPlayer, call: libCall) -> None:
        assert_type(player, libPlayer)
        assert_type(call, libCall)

        if self.is_abandoned:
            msg = f"Hand {self} is abandoned: {self.abandoned_because}"
            raise AuctionError(msg)

        self._check_for_expired_tournament()

        auction = self.auction
        try:
            auction.raise_if_illegal_call(player=player, call=call)
        except AuctionException as e:
            raise AuctionError(str(e)) from e

        modelCall = self.call_set.create(serialized=call.serialize())

        self.send_event_to_players_and_hand(
            data={
                "new-call": {
                    "serialized": call.serialize(),
                    "seat_pk": modelCall.seat_pk,
                },
            },
        )

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
        elif self.get_xscript().final_score() is not None:
            Tournament.objects.get_or_create_tournament_open_for_signups()
            self.send_event_to_players_and_hand(
                data={
                    "table": self.table.pk,
                    "final_score": "Passed Out",
                },
            )

    def add_play_from_player(self, *, player: libPlayer, card: libCard) -> Play:
        assert_type(player, libPlayer)
        assert_type(card, libCard)

        if self.is_abandoned:
            msg = f"Hand {self} is abandoned: {self.abandoned_because}"
            raise PlayError(msg)

        self._check_for_expired_tournament()

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

        data: dict[str, Any] = {
            "new-play": {
                "serialized": card.serialize(),
                "seat_pk": rv.seat_pk,
            },
        }

        if self.get_xscript().num_plays == 1:  # opening lead
            assert self.dummy is not None
            libCards = sorted(self.current_cards_by_seat()[self.dummy.seat])
            data["dummy"] = "".join([c.serialize() for c in libCards])

        self.send_event_to_players_and_hand(data=data)

        final_score = self.get_xscript().final_score()

        if final_score is not None:
            self.table.tournament.maybe_complete()

            Tournament.objects.get_or_create_tournament_open_for_signups()
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
            assert libAllowed is not None
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
        if seat_who_may_play is None:
            return None
        pbs = self.libPlayers_by_seat
        return Player.objects.get_by_name(pbs[seat_who_may_play].name)

    def modPlayer_by_seat(self, seat: libSeat) -> Player:
        modelPlayer = self.players_by_direction[seat.value]
        return Player.objects.get_by_name(modelPlayer.name)

    @property
    def player_names_string(self) -> str:
        return ", ".join([p.name for p in self.players_by_direction.values()])

    @cached_property
    def players_by_direction(self) -> dict[str, Player]:
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
        cc = collections.Counter([p.seat.value for p in self.annotated_plays if p.winner])
        ns = cc["S"] + cc["N"]
        ew = cc["E"] + cc["W"]
        return {"N/S": ns, "E/W": ew}

    # This is meant for use by get_xscript; anyone else who wants to examine our plays should call that.
    @property
    def plays(self):
        return self.play_set.order_by("id")

    def toggle_open_access(self) -> None:
        if self.is_abandoned:
            return None

        self.open_access = not self.open_access
        self.save()
        self.send_event_to_players_and_hand(data={"open-access-status": self.open_access})

    # The summary is phrased in terms of the player, who is presumed to have played the board already -- except if it's
    # None, in which case we (arbitrarily) summarize in terms of North.
    def summary_as_viewed_by(self, *, as_viewed_by: Player | None) -> tuple[str, str | int]:
        if as_viewed_by is None:
            if not self.board.tournament.is_complete:
                return "Remind me -- who are you, again?", "-"

        if as_viewed_by is not None:
            if self.board.what_can_they_see(
                player=as_viewed_by
            ) != self.board.PlayerVisibility.everything and as_viewed_by.name not in {
                p.name for p in self.players_by_direction.values()
            }:
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
        my_hand_for_this_board = None

        if as_viewed_by is not None:
            my_hand_for_this_board = as_viewed_by.hand_at_which_board_was_played(self.board)
        if my_hand_for_this_board is not None:
            my_seat = my_hand_for_this_board.table.seats.filter(player=as_viewed_by).first()
        fs = self.get_xscript().final_score()

        if fs is None:
            total_score = "-"
            trick_summary = "still being played"
        elif fs == 0:
            total_score = 0
            trick_summary = "Passed Out"
        else:
            trick_summary = fs.trick_summary

            if getattr(my_seat, "direction", None) in {None, 1, 3}:  # north/south
                total_score = fs.north_south_points or -fs.east_west_points
            else:
                total_score = fs.east_west_points or -fs.north_south_points

        return (f"{auction_status}: {trick_summary}", total_score)

    def __str__(self) -> str:
        return f"Tournament #{self.table.tournament.display_number}, table {self.table.pk}, board#{self.board.display_number}"

    @staticmethod
    def untaint_board(*, instance, **kwargs):
        for p in instance.players():
            p.boards_played.remove(instance.board)
        logger.debug(
            "Hand %s un-tainted board %s from %s.",
            instance.pk,
            instance.board.pk,
            [p.name for p in instance.players()],
        )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["board", "table"],
                name="%(app_label)s_%(class)s_a_board_can_be_played_only_once_at_a_given_table",
            ),
        ]


@admin.register(Hand)
class HandAdmin(admin.ModelAdmin):
    list_display = ["table", "board", "open_access", "is_abandoned"]
    list_filter = ["open_access"]


class CallManager(models.Manager):
    def create(self, *args, **kwargs) -> Call:
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
    def seat_pk(self) -> PK | None:
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
    def seat_pk(self) -> PK | None:
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
