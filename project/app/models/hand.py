from __future__ import annotations

import collections
from collections.abc import Generator
import dataclasses
import datetime
import json
import logging
import time
from typing import TYPE_CHECKING, Any, Iterable

import more_itertools
from bridge.auction import Auction
from bridge.auction import AuctionException
from bridge.card import Card as libCard
from bridge.card import Suit as libSuit
from bridge.contract import Bid as libBid
from bridge.contract import Call as libCall
from bridge.contract import Contract as libContract
from bridge.seat import Seat
from bridge.table import Hand as libHand
from bridge.table import Player as libPlayer
from bridge.table import Table as libTable
from bridge.xscript import CBS, HandTranscript
from django.contrib import admin
from django.core.cache import cache
from django.db import Error, models, transaction
from django.db.models import Q
from django.db.models.query import QuerySet
from django.http import Http404
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.html import format_html
from django.utils import timezone
from django_eventstream import send_event  # type: ignore [import-untyped]
from django_extensions.db.models import TimeStampedModel  # type: ignore [import-untyped]
from django_prometheus.models import ExportModelOperationsMixin  # type: ignore [import-untyped]


from ..utils import movements
from .common import attribute_names
from .player import Player
from .tournament import Tournament

from .types import PK, PK_from_str
from .utils import assert_type

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

    from django.db.models.manager import RelatedManager

logger = logging.getLogger(__name__)


class AuctionError(Exception):
    pass


class HandError(Exception):
    pass


class PlayError(Exception):
    pass


class TournamentIsOver(HandError):
    pass


class RoundIsOver(HandError):
    pass


@dataclasses.dataclass
class TrickTuple:
    seat: Seat
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
    holdings_by_seat: dict[Seat, AllFourSuitHoldings]

    def items(self) -> Iterable[tuple[Seat, AllFourSuitHoldings]]:
        return self.holdings_by_seat.items()

    def __getitem__(self, seat: Seat) -> AllFourSuitHoldings:
        assert_type(seat, Seat)
        return self.holdings_by_seat[seat]


def summarize(thing):
    if isinstance(thing, str):
        ellipses = ""
        if len(thing) > 20:
            ellipses = "..."
        return thing[0:20] + ellipses
    elif isinstance(thing, dict):
        return {k: summarize(v) for k, v in thing.items()}
    elif isinstance(thing, list):
        return [summarize(elt) for elt in thing]
    else:
        return thing


def send_timestamped_event(
    *, channel: str, data: dict[str, Any], when: float | None = None
) -> None:
    if when is None:
        when = time.time()

    # logger.debug(f"Sending {summarize(data)=} to {channel=}")
    send_event(channel=channel, event_type="message", data=data | {"time": when})


def enrich(qs: QuerySet) -> QuerySet:
    amended_attr_names = [f"{a}__user" for a in attribute_names]
    return qs.select_related("board", "board__tournament", *attribute_names, *amended_attr_names)


class HandManager(models.Manager):
    from . import Board

    def _update_redundant_fields(self):
        for instance in self.all():
            instance._update_redundant_fields()

    def prepop(self) -> QuerySet:
        return enrich(self)

    # Like django.shortcuts.get_object_or_404(app.models.Hand, pk=pk), but does a buncha "select_related" for efficiency.
    def get_or_404(self, pk: PK) -> Hand:
        try:
            return self.prepop().get(pk=pk)
        except Hand.DoesNotExist:
            raise Http404("No Hand matches the given query.")

    def _create_hand_with(
        self, *, pnb: movements.PlayersAndBoardsForOneRound, board: Board
    ) -> Hand | None:
        q = pnb.quartet
        ns = q.ns
        ew = q.ew
        n_k, s_k = ns.id_
        e_k, w_k = ew.id_
        North = Player.objects.get(pk=n_k)
        East = Player.objects.get(pk=e_k)
        South = Player.objects.get(pk=s_k)
        West = Player.objects.get(pk=w_k)

        new_hand = self.create(
            board=board,
            North=North,
            East=East,
            South=South,
            West=West,
            table_display_number=pnb.table_number,
        )

        return new_hand

    def create_next_hand_at_table(
        self, tournament: Tournament, zb_table_number: int, zb_round_number: int
    ) -> Hand | None:
        with transaction.atomic():
            hands_already_played_at_this_table = self.filter(
                board__group=movements._group_letter(zb_round_number),
                board__tournament=tournament,
                table_display_number=zb_table_number + 1,
            )

            boards_already_played_at_this_table = set(
                [h.board for h in hands_already_played_at_this_table]
            )

            mvmt = tournament.get_movement()

            pnb = mvmt.players_and_boards_for(
                zb_round_number=zb_round_number, zb_table_number=zb_table_number
            )
            for candidate_board in pnb.board_group.boards:
                if candidate_board not in boards_already_played_at_this_table:
                    return self._create_hand_with(pnb=pnb, board=candidate_board)

            return None

    def create(self, *args, **kwargs) -> Hand:
        board = kwargs.get("board")
        assert board is not None

        players = [kwargs[direction] for direction in attribute_names]

        p: Player
        for p in players:
            if p.current_hand is not None and not p.current_hand.is_complete:
                msg = f"Cannot seat {p.name} because they are currently playing {p.current_hand}"
                raise HandError(msg)

            if (h := p.hand_at_which_we_played_board(board)) is not None:
                msg = (
                    f"Whoa buddy: {p.name} has already played board #{board.display_number} at {h}"
                )
                raise HandError(msg)

        rv = super().create(*args, **kwargs)
        rv.last_action_time = rv.created
        rv.save()

        for direction in attribute_names:
            p = kwargs[direction]
            p.current_hand = rv
            p.save()

        logger.debug(
            "New hand: %s, played by %s",
            rv,
            [p.name for p in players],
        )

        return rv


class Hand(ExportModelOperationsMixin("hand"), TimeStampedModel):  # type: ignore[misc]
    """All the calls and plays for a given hand."""

    if TYPE_CHECKING:
        call_set = RelatedManager["Call"]()
        play_set = RelatedManager["Play"]()
    direction_names = attribute_names
    objects = HandManager()

    from . import Board

    board = models.ForeignKey[Board]("Board", on_delete=models.CASCADE)

    # This field is redundant, in that we could compute it on-demand from the transcript.  But I suspect that is slow.
    is_complete = models.BooleanField(default=False)

    North = models.ForeignKey["Player"](
        "Player",
        on_delete=models.CASCADE,
        related_name="north",
    )
    East = models.ForeignKey["Player"](
        "Player",
        on_delete=models.CASCADE,
        related_name="east",
    )
    South = models.ForeignKey["Player"](
        "Player",
        on_delete=models.CASCADE,
        related_name="south",
    )
    West = models.ForeignKey["Player"](
        "Player",
        on_delete=models.CASCADE,
        related_name="west",
    )

    table_display_number = models.SmallIntegerField()

    open_access = models.BooleanField(
        default=False,
        db_comment='For debugging only! Settable via the admin site, and maaaaybe by a special "god-mode" switch in the UI',
    )  # type: ignore

    abandoned_because = models.CharField(max_length=200, null=True)

    last_action_time = models.DateTimeField(default=timezone.now)

    def _update_redundant_fields(self):
        x = self.get_xscript()
        self.is_complete = (x.auction.status is Auction.PassedOut) or x.num_plays == 52
        self.save(update_fields=["is_complete"])

    def as_link(self):
        return format_html(
            "<a href='{}'>{}</a>",
            reverse("app:hand-dispatch", kwargs={"pk": self.pk}),
            str(self),
        )

    @cached_property
    def tournament(self) -> Tournament:
        return self.board.tournament

    def last_action(self) -> tuple[datetime.datetime, str]:
        rv = (self.created, "joined hand")
        if (
            most_recent_call_time := self.calls.aggregate(models.Min("created"))["created__min"]
        ) is not None:
            if most_recent_call_time > rv[0]:  # it better be, but you never know
                rv = (most_recent_call_time, "called")
        if (
            most_recent_play_time := self.plays.aggregate(models.Min("created"))["created__min"]
        ) is not None:
            if most_recent_play_time > rv[0]:
                rv = (most_recent_play_time, "played")
        return rv

    def _check_for_expired_tournament(self) -> None:
        tour = self.tournament
        if tour.play_completion_deadline_has_passed():
            deadline = tour.play_completion_deadline
            assert deadline is not None

            tour.completed_at = tour.play_completion_deadline
            tour.save()

            msg = f"Tournament #{tour.display_number}'s play completion deadline ({deadline.isoformat()}) has passed!"
            raise HandError(msg)

    @property
    def event_table_html_channel(self):
        return f"table:html:{self.pk}"

    @staticmethod
    def hand_pk_from_event_table_html_channel(cn: str) -> PK | None:
        pieces = cn.split("table:html:")
        if len(pieces) != 2:
            return None
        return PK_from_str(pieces[1])

    @property
    @admin.display
    def is_abandoned(self) -> bool:
        return self.abandoned_because is not None

    def status_string(self) -> str:
        if self.is_complete:
            return "✔"
        if self.is_abandoned:
            return "✘"
        return "…"

    def send_HTML_to_player(self, *, player: Player, data: dict[str, Any]) -> None:
        send_timestamped_event(channel=player.event_HTML_hand_channel, data=data)

    def send_JSON_to_players(self, *, data: dict[str, Any]) -> None:
        for p in self.players():
            send_timestamped_event(channel=p.event_JSON_hand_channel, data=data)

    def send_event_to_all_players(self, *, data: dict[str, Any]) -> None:
        now = time.time()
        for p in self.players():
            self.send_event_to_player(player_pk=p.pk, data=data, now=now)

    def send_event_to_player(
        self, *, player_pk: PK, data: dict[str, Any], now: float | None = None
    ) -> None:
        if now is None:
            now = time.time()

        p = Player.objects.get(pk=player_pk)
        player_channel = p.event_HTML_hand_channel

        send_timestamped_event(channel=player_channel, data=data | {"hand_pk": self.pk}, when=now)

    # These attributes are set by view code.  The values come from method calls that take a Player as an argument; we do
    # this because it's not possible for the template to invoke a method that requires an argument.
    summary_for_this_viewer: str
    score_for_this_viewer: str | int

    @cached_property
    def libPlayers_by_libSeat(self) -> dict[Seat, libPlayer]:
        assert self.North is not None
        assert self.East is not None
        assert self.South is not None
        assert self.West is not None

        return {
            Seat.NORTH: libPlayer(
                seat=Seat.NORTH,
                name=self.North.name,
            ),
            Seat.EAST: libPlayer(
                seat=Seat.EAST,
                name=self.East.name,
            ),
            Seat.SOUTH: libPlayer(
                seat=Seat.SOUTH,
                name=self.South.name,
            ),
            Seat.WEST: libPlayer(
                seat=Seat.WEST,
                name=self.West.name,
            ),
        }

    @cached_property
    def lib_table_with_cards_as_dealt(self) -> libTable:
        players = list(self.libPlayers_by_libSeat.values())
        for p in players:
            assert_type(p, libPlayer)
        return libTable(players=players)

    def _cache_key(self) -> str:
        return f"hand:{self.pk}"

    def _cache_set(self, value: HandTranscript) -> None:
        assert_type(value, HandTranscript)
        cache.set(self._cache_key(), value)

    def _cache_get(self) -> HandTranscript | None:
        rv = cache.get(self._cache_key())
        assert_type(rv, HandTranscript | None)
        return rv

    def get_xscript(self) -> HandTranscript:
        def calls() -> Iterator[tuple[libPlayer, libCall]]:
            for seat, call in self.annotated_calls:
                player = self.libPlayers_by_libSeat[seat]
                yield (player, call.libraryThing)

        if (_xscript := self._cache_get()) is None:
            lib_table = self.lib_table_with_cards_as_dealt
            auction = Auction(table=lib_table, dealer=Seat(self.board.dealer))
            dealt_cards_by_seat: CBS = {
                Seat(direction): self.board.cards_for_direction_letter(direction)
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

        return _xscript

    def serializable_xscript(self) -> Any:
        return self.get_xscript().serializable()

    def add_call(self, *, call: libCall) -> None:
        assert_type(call, libCall)

        if self.is_abandoned:
            msg = f"Hand {self} is abandoned: {self.abandoned_because}"
            raise AuctionError(msg)

        self._check_for_expired_tournament()

        player = self.player_who_may_call
        if player is None:
            raise AuctionError("Nobody may call now")

        try:
            the_call = self.call_set.create(serialized=call.serialize())
        except (Error, AuctionException) as e:
            raise AuctionError(str(e)) from e

        self.last_action_time = the_call.created
        self.save()

        logger.debug(
            "%s: %s (%d) called %s; last_action_time is %s",
            self,
            player,
            player.pk,
            call,
            self.last_action_time,
        )

        now = time.time()

        for p in self.players():
            send_timestamped_event(
                channel=p.event_HTML_hand_channel,
                data={
                    "bidding_box_html": self._get_current_bidding_box_html_for_player(p),
                    "hand_pk": self.pk,
                },
                when=now,
            )

        self.send_JSON_to_players(
            data={
                "hand_event": self.call_set.count() - 1,
                "hand_pk": self.pk,
                "new-call": {"serialized": call.serialize()},
                "tempo_seconds": self.board.tournament.tempo_seconds,
            }
        )

        from app.views.hand import auction_history_HTML_for_table

        send_timestamped_event(
            channel=self.event_table_html_channel,
            data={"auction_history_html": auction_history_HTML_for_table(hand=self)},
            when=now,
        )

        if self.declarer:  # the auction just settled
            contract = self.auction.status
            assert isinstance(contract, libContract)
            assert contract.declarer is not None

            data = {
                "contract_text": str(contract),
                "contract": {
                    "opening_leader": contract.declarer.seat.lho().value,
                },
            }

            self.send_JSON_to_players(data=data)

            # The interactive hand page needs this to know that it's time to reload, in order to show the "play" slides.
            # Yeah, I know; it's not HTML.  :shrug:
            send_timestamped_event(channel=self.event_table_html_channel, data=data)

        elif self.get_xscript().final_score() is not None:
            self.do_end_of_hand_stuff(final_score_text="Passed Out")

    def add_play_from_model_player(self, *, player: Player, card: libCard) -> Play:
        assert_type(player, Player)
        assert_type(card, libCard)

        if self.is_abandoned:
            msg = f"Hand {self} is abandoned: {self.abandoned_because}"
            raise PlayError(msg)

        self._check_for_expired_tournament()

        if self.next_seat_to_play is None:
            msg = "Nobody may play now"
            raise PlayError(msg)

        whose_turn = self.player_who_controls_seat(self.next_seat_to_play, right_this_second=True)
        if player != whose_turn:
            raise PlayError(
                f"It's not {player.name}'s turn to play, but rather {whose_turn}'s (at {self.next_seat_to_play})"
            )

        seat_that_just_played = self.next_seat_to_play

        try:
            rv = self.play_set.create(hand=self, serialized=card.serialize())
        except Error as e:
            raise PlayError(str(e)) from e

        self.last_action_time = rv.created
        self.save()

        logger.debug(
            "%s: %s (%d) played %s",
            self,
            player,
            player.pk,
            card,
        )

        self.send_JSON_to_players(
            data={
                "hand_event": self.call_set.count() + self.play_set.count() - 1,
                "new-play": {
                    "hand_pk": self.pk,
                    "serialized": card.serialize(),
                },
                "tempo_seconds": self.board.tournament.tempo_seconds,
            }
        )

        send_timestamped_event(
            channel=self.event_table_html_channel,
            data={
                "trick_counts_string": self.trick_counts_string(),
                "trick_html": self._get_current_trick_html(),
            },
        )

        if (final_score := self.get_xscript().final_score()) is not None:
            self.do_end_of_hand_stuff(final_score_text=str(final_score))
        else:
            self.send_HTML_update_to_appropriate_channels(last_seat=seat_that_just_played)

        return rv

    def _get_current_bidding_box_html_for_player(self, p: Player) -> str:
        from app.views.hand import _bidding_box_HTML_for_hand_for_player

        return _bidding_box_HTML_for_hand_for_player(self, p)

    def _get_current_trick_html(self) -> str:
        from app.views.hand import _three_by_three_HTML_for_trick

        return _three_by_three_HTML_for_trick(self)

    def _get_current_seat_html(self, *, seat: Seat, viewer_may_control_this_seat: bool) -> str:
        from app.views.hand import _hand_HTML_for_seat

        return _hand_HTML_for_seat(
            hand=self,
            seat=seat,
            viewer_may_control_this_seat=viewer_may_control_this_seat,
        )

    @staticmethod
    def has_player(player: Player) -> Q:
        expression = Q(pk__in=[])
        for direction in attribute_names:
            expression |= Q(**{direction: player})

        return expression

    def send_HTML_update_to_appropriate_channels(self, *, last_seat: Seat) -> None:
        current_seat = self.next_seat_to_call or self.next_seat_to_play

        for seat in (last_seat, current_seat):
            if seat is None:
                assert self.is_complete or self.is_abandoned, (
                    f"{self} is neither complete nor abandoned; yet there is no current seat??"
                )
                continue

            controlling_player = self.player_who_controls_seat(seat, right_this_second=False)
            recipients: Iterable[Player]
            if self.dummy is not None and seat == self.dummy.seat:
                recipients = self.players()
            else:
                recipients = [controlling_player]

            for r in recipients:
                self.send_HTML_to_player(
                    data={
                        "current_hand_direction": seat.name,
                        "current_hand_html": self._get_current_seat_html(
                            seat=seat,
                            viewer_may_control_this_seat=r == controlling_player,
                        ),
                    },
                    player=r,
                )

    def do_end_of_hand_stuff(self, *, final_score_text: str) -> None:
        with transaction.atomic():
            assert self.is_complete
            assert self.table_display_number is not None

            self.send_JSON_to_players(
                data={
                    "final_score": final_score_text,
                },
            )

            if (num_complete_rounds := self.tournament.the_round_just_ended()) is not None:
                mvmt = self.tournament.get_movement()

                if num_complete_rounds < mvmt.num_rounds:
                    self.tournament.create_hands_for_round(zb_round_number=num_complete_rounds)
                else:
                    self.tournament.maybe_complete()

            else:
                board_group = getattr(self.board, "group", "?")
                new_hand = Hand.objects.create_next_hand_at_table(
                    tournament=self.tournament,
                    zb_table_number=self.table_display_number - 1,
                    zb_round_number=movements._zb_round_number(board_group),
                )
                if new_hand is not None:
                    logger.info(f"Just created new hand {new_hand}")
                else:
                    logger.info(
                        f"We've played all the boards in tournament #{self.tournament.display_number}, board group {self.board.group}, at table #{self.table_display_number}"
                    )

    @property
    def auction(self) -> Auction:
        return self.get_xscript().auction

    @property
    def declarer(self) -> libPlayer | None:
        if not self.auction.found_contract:
            return None
        return self.auction.declarer

    @property
    def model_declarer(self) -> Player | None:
        libDeclarer = self.declarer
        if libDeclarer is None:
            return None
        return getattr(self, libDeclarer.seat.name)

    @property
    def dummy(self) -> libPlayer | None:
        if not self.auction.found_contract:
            return None
        return self.auction.dummy

    @property
    def model_dummy(self) -> Player | None:
        libDummy = self.dummy
        if not libDummy:
            return None
        return getattr(self, libDummy.seat.name)

    @property
    def next_seat_to_call(self) -> Seat | None:
        if self.is_abandoned:
            return None

        if self.auction.status is Auction.Incomplete:
            libAllowed = self.auction.allowed_caller()
            assert libAllowed is not None
            return libAllowed.seat

        return None

    @property
    def player_who_may_call(self) -> Player | None:
        s = self.next_seat_to_call
        if s is None:
            return None
        return getattr(self, s.name)

    # TODO -- this method might be confusing: it doesn't know that declarer control's dummy's hand.
    # Best to use next_seat_to_play when possible.
    @property
    def player_who_may_play(self) -> Player | None:
        if self.is_abandoned:
            return None

        if not self.auction.found_contract:
            return None

        seat_who_may_play = self.get_xscript().next_seat_to_play()
        if seat_who_may_play is None:
            return None

        return getattr(self, seat_who_may_play.name)

    @property
    def active_seat_name(self) -> str:
        if (nsp := self.next_seat_to_play) is not None:
            return nsp.name

        return ""

    def player_who_controls_seat(self, seat: Seat, right_this_second: bool) -> Player:
        for d in self.direction_names:
            p: Player = getattr(self, d)
            assert p.current_hand == self, (
                f"So like {p.name}'s current hand is {p.current_hand=}, but I am {self=}"
            )
            if p.controls_seat(seat=seat, right_this_second=right_this_second):
                return p

        raise Exception(
            f"Internal error: no player controls {seat.name=} of hand {self} ({self.pk=})"
        )

    @property
    def next_seat_to_play(self) -> Seat | None:
        if not self.auction.found_contract:
            return None

        xscript = self.get_xscript()
        return xscript.next_seat_to_play()

    def modPlayer_by_seat(self, seat: Seat) -> Player:
        return getattr(self, seat.name)

    # Do `Hand.objects.select_related(*attribute_names)` when fetching users, lest you do lots of extra queries.
    def players(self) -> Generator[Player]:
        for attribute_name in attribute_names:
            yield getattr(self, attribute_name)

    def player_pks(self) -> list[PK]:
        # Slight kludge -- I used to have `getattr(self, direction).pk`, but that fetched each player from the db, then
        # threw away everything but the pk.
        return [getattr(self, f"{direction}_id") for direction in self.direction_names]

    @property
    def player_names_string(self) -> str:
        return ", ".join([p.name for p in self.players_by_direction_letter.values()])

    @cached_property
    def players_by_direction_letter(self) -> dict[str, Player]:
        return {
            direction[0].upper(): getattr(self, direction) for direction in self.direction_names
        }

    @cached_property
    def direction_letters_by_player(self) -> dict[Player, str]:
        return {v: k for k, v in self.players_by_direction_letter.items()}

    def current_cards_by_seat(self, *, as_dealt: bool = False) -> dict[Seat, set[libCard]]:
        rv = {}
        for direction_letter, cardstring in self.board.hand_strings_by_direction_letter.items():
            seat = Seat(direction_letter)
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
            assert_type(seat, Seat)

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

    def serialized_calls(self):
        return [c.serialized for c in self.call_set.order_by("id")]

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
        seat_cycle = Seat.cycle()
        while True:
            s = next(seat_cycle)

            # The first call is made by dealer.
            if s.lho().value == self.board.dealer:
                return seat_cycle

    @property
    def annotated_calls(self) -> Iterable[tuple[Seat, Call]]:
        return list(
            zip(
                self._seat_cycle_starting_with_dealer,
                self.calls.all(),
            ),
        )

    @property
    def last_annotated_call(self) -> tuple[Seat, Call]:
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

    def trick_counts_string(self) -> str:
        cc = collections.Counter([p.seat.value for p in self.annotated_plays if p.winner])
        ns = cc["S"] + cc["N"]
        ew = cc["E"] + cc["W"]
        return json.dumps({"N/S": ns, "E/W": ew})

    # This is meant for use by get_xscript; anyone else who wants to examine our plays should call that.
    @property
    def plays(self):
        return self.play_set.order_by("id")

    def _score_by_player(self, *, player: Player) -> int:
        fs = self.get_xscript().final_score()
        assert fs is not None

        if fs == 0:
            return 0

        letter = self.direction_letters_by_player[player]
        return fs.north_south_points if letter in "NS" else fs.east_west_points

    def matchpoints_for_partnership(self, *, one_player: Player) -> int:
        if one_player not in self.players():
            return 0

        our_score = self._score_by_player(player=one_player)

        matchpoints = 0

        for oh in self.board.hand_set.exclude(pk=self.pk):
            other_player = oh.players_by_direction_letter[
                self.direction_letters_by_player[one_player]
            ]
            if our_score > oh._score_by_player(player=other_player):
                matchpoints += 2
            elif our_score == oh._score_by_player(player=other_player):
                matchpoints += 1

        return matchpoints

    # The summary is phrased in terms of the player, if they have seen (at least some of) the board already; otherwise
    # we (arbitrarily) summarize in terms of North.
    def summary_as_viewed_by(self, *, as_viewed_by: Player | None) -> tuple[str, str | int]:
        if as_viewed_by is None:
            if not self.tournament.is_complete:
                return "Remind me -- who are you, again?", "-"

        if as_viewed_by is not None:
            if self.board.what_can_they_see(
                player=as_viewed_by
            ) != self.board.PlayerVisibility.everything and as_viewed_by.pk not in {
                p.pk for p in self.players_by_direction_letter.values()
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

        total_score: int | str = "-"

        my_seat_letter = "N"

        if as_viewed_by is not None:
            if (direction := self.direction_letters_by_player.get(as_viewed_by)) is not None:
                my_seat_letter = direction

        fs = self.get_xscript().final_score()

        if fs is None:
            trick_summary = "still being played"
        elif fs == 0:
            total_score = 0
            trick_summary = "Passed Out"
        else:
            trick_summary = fs.trick_summary

            if my_seat_letter in "NS":
                total_score = fs.north_south_points or -fs.east_west_points
            else:
                total_score = fs.east_west_points or -fs.north_south_points

        return (f"{auction_status}: {trick_summary}", total_score)

    def save(self, *args, **kwargs) -> None:
        super().save(**kwargs)
        if self.abandoned_because is None:
            for attribute_name in attribute_names:
                p: Player = getattr(self, attribute_name)
                p.current_hand = self  # type: ignore [assignment]
                p.save()

    def __str__(self) -> str:
        return f"Tournament #{self.tournament.display_number}, Table #{self.table_display_number}, board#{self.board.display_number}"

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["board", "North", "East", "South", "West"],
                name="%(app_label)s_%(class)s_a_board_can_be_played_only_once_by_four_players",
            ),
            models.UniqueConstraint(
                fields=["board", "table_display_number"],
                name="%(app_label)s_%(class)s_a_board_can_be_played_only_once_at_a_given_table",
            ),
        ]
        ordering = [
            "board__tournament__display_number",
            "table_display_number",
            "board__display_number",
        ]


@admin.register(Hand)
class HandAdmin(admin.ModelAdmin):
    list_display = ["board", "open_access", "is_abandoned"]
    list_filter = ["open_access"]


class CallManager(models.Manager):
    def create(self, *args, **kwargs) -> Call:
        h: Hand = kwargs["hand"]

        x: HandTranscript = h.get_xscript()

        c = libBid.deserialize(kwargs["serialized"])
        x.add_call(c)

        rv = super().create(*args, **kwargs)

        h._cache_set(x)

        if x.auction.status is Auction.PassedOut:
            h.is_complete = True
            h.save()

        return rv


class Call(ExportModelOperationsMixin("call"), TimeStampedModel):  # type: ignore[misc]
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

    def __str__(self) -> str:
        return str(self.libraryThing)


admin.site.register(Call)


class PlayManager(models.Manager):
    def create(self, *args, **kwargs) -> Play:
        """Only Hand.add_play_from_model_player may call me; the rest of y'all should call *that*."""
        h: Hand = kwargs["hand"]

        x: HandTranscript = h.get_xscript()

        card = libCard.deserialize(kwargs["serialized"])

        x.add_card(card)

        rv = super().create(*args, **kwargs)

        h._cache_set(x)

        if x.num_plays == 52:
            h.is_complete = True
            h.save()

        return rv


class Play(ExportModelOperationsMixin("play"), TimeStampedModel):  # type: ignore[misc]
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

    @cached_property
    def seat(self) -> Seat:
        for tt in self.hand.annotated_plays:
            if self.serialized == tt.card.serialize():
                return tt.seat

        msg = f"Internal error, cannot find {self.serialized} in {[p.card for p in self.hand.annotated_plays]}"
        raise Exception(msg)


admin.site.register(Play)
