from __future__ import annotations

import collections
from collections.abc import Callable
import dataclasses
import datetime
import json
import logging
import time
from typing import TYPE_CHECKING, Any

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
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.html import format_html
from django_eventstream import send_event  # type: ignore [import-untyped]
from django_extensions.db.models import TimeStampedModel  # type: ignore [import-untyped]

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


def send_timestamped_event(
    *, channel: str, data: dict[str, Any], when: float | None = None
) -> None:
    if when is None:
        when = time.time()

    def summarize(thing):
        if isinstance(thing, str):
            return thing[0:20]
        elif isinstance(thing, dict):
            return {k: summarize(v) for k, v in thing.items()}
        else:
            return thing

    # logger.debug(f"Sending {summarize(data)=} to {channel=}")
    send_event(channel=channel, event_type="message", data=data | {"time": when})


class HandManager(models.Manager):
    from . import Board

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
        for p in (North, East):
            for x in (p, p.partner):
                if x.current_hand() is not None:
                    new_hand_description = ", ".join([str(p) for p in (North, East, South, West)])
                    new_hand_description += f" play {board} at {pnb.table_number}"
                    msg = f"Cannot seat {new_hand_description} when {x} is still playing {x.current_hand()}"
                    logger.info("%s; returning None", msg)
                    return None

            p.unseat_partnership(reason=f"New hand for round {pnb.zb_round_number + 1}")
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
                table_display_number=zb_table_number + 1,
                board__group=movements._group_letter(zb_round_number),
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
            if (ch := p.current_hand_and_direction()) is not None:
                msg = f"Cannot seat {p.name} because they are already playing {ch[1]} in {ch[0]}"
                raise HandError(msg)

            # TODO -- figure out why this triggers! I expected this to trigger only if our caller was entirely on drugs,
            # but in fact it triggers reliably when I do `just stress --min-players=20`
            if (h := p.hand_at_which_we_played_board(board)) is not None:
                msg = (
                    f"Whoa buddy: {p.name} has already played board #{board.display_number} at {h}"
                )
                raise HandError(msg)

        rv = super().create(*args, **kwargs)

        logger.debug(
            "New hand: %s, played by %s",
            rv,
            [p.name for p in players],
        )

        for p in players:
            p._control_bot()

        return rv


# fmt:off

# fmt:on
class Hand(TimeStampedModel):
    """All the calls and plays for a given hand."""

    if TYPE_CHECKING:
        call_set = RelatedManager["Call"]()
        play_set = RelatedManager["Play"]()
    direction_names = attribute_names
    objects = HandManager()

    from . import Board

    board = models.ForeignKey[Board]("Board", on_delete=models.CASCADE)

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

    def as_link(self):
        return format_html(
            "<a href='{}'>{}</a>",
            reverse("app:hand-detail", kwargs={"pk": self.pk}),
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

            tour.is_complete = True
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

    @cached_property
    @admin.display
    def is_abandoned(self) -> bool:
        if self.is_complete:
            return False

        if self.abandoned_because is not None:
            return True

        tournament: Tournament = self.tournament
        if not tournament.is_complete and tournament.play_completion_deadline_has_passed():
            self.abandoned_because = f"Tournament #{tournament.display_number}'s play deadline {tournament.play_completion_deadline} has passed"
            self.save()
            return True

        def has_defected(p: Player) -> bool:
            their_hands = p.hands_played.all()

            h: Hand
            for h in their_hands:
                if h.is_complete or h.abandoned_because is not None:
                    continue
                if h.pk != self.pk:
                    return True

            return False

        defectors = [p for p in self.players() if has_defected(p)]
        if defectors:
            self.abandoned_because = (
                f"{[p.name for p in defectors]} have started playing some other hand(s)"
            )
            logger.info(
                "I just realized that %s is abandoned because %s", self, self.abandoned_because
            )
            self.save()
            return True

        return False

    def send_HTML_to_table(self, *, data: dict[str, Any]) -> None:
        send_timestamped_event(channel=self.event_table_html_channel, data=data)

    def send_HTML_to_player(self, *, player_pk: PK, data: dict[str, Any]) -> None:
        p = Player.objects.get(pk=player_pk)
        send_timestamped_event(channel=p.event_HTML_hand_channel, data=data)

    def send_JSON_to_players(self, *, data: dict[str, Any]) -> None:
        for p in self.players():
            send_timestamped_event(channel=p.event_JSON_hand_channel, data=data)

    def send_events_to_players_and_hand(self, *, data: dict[str, Any]) -> None:
        table_channel = self.event_table_html_channel
        player_channels: list[str] = []
        for p in self.players():
            player_channels.append(p.event_HTML_hand_channel)
            player_channels.append(p.event_JSON_hand_channel)

        all_channels = [table_channel, "all-tables", *player_channels]

        data = data.copy()
        data["hand_pk"] = self.pk
        now = time.time()
        for channel in all_channels:
            send_timestamped_event(channel=channel, data=data, when=now)

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

    def _cache_set(self, value: str) -> None:
        cache.set(self._cache_key(), value)

    def _cache_get(self) -> Any:
        return cache.get(self._cache_key())

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

        self.call_set.create(serialized=call.serialize())

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

            send_timestamped_event(
                channel=p.event_JSON_hand_channel,
                data={
                    "hand_pk": self.pk,
                    "new-call": {"serialized": call.serialize()},
                },
                when=now,
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

            # TODO -- html-escape it, I guess
            self.send_HTML_to_table(data=data)
        elif self.get_xscript().final_score() is not None:
            self.do_end_of_hand_stuff(final_score_text="Passed Out")

    def _get_current_bidding_box_html_for_player(self, p: Player) -> str:
        from app.views.hand import _bidding_box_HTML_for_hand_for_player

        return _bidding_box_HTML_for_hand_for_player(self, p)

    def _get_current_trick_html(self) -> str:
        from app.views.hand import _three_by_three_HTML_for_trick

        return _three_by_three_HTML_for_trick(self)

    def _get_current_hand_html(self, *, p: Player) -> str:
        from app.views.hand import _hand_HTML_for_player

        return _hand_HTML_for_player(hand=self, player=p)

    def send_HTML_update_to_appropriate_channel(self, *, player_to_update: Player | None) -> None:
        if player_to_update is None:
            return

        if player_to_update.current_direction() is None:
            return

        assert self.dummy is not None
        dummy_direction_letter = self.dummy.seat.name[0]

        method: Callable[..., None]

        if player_to_update == self.players_by_direction_letter[dummy_direction_letter]:
            method = self.send_HTML_to_table
            kwargs = dict(
                data={
                    "dummy_direction": self.dummy.seat.name,
                    "dummy_html": self._get_current_hand_html(p=player_to_update),
                }
            )
        else:
            method = self.send_HTML_to_player
            kwargs = dict(
                data={
                    "current_hand_direction": player_to_update.libraryThing().seat.name,
                    "current_hand_html": self._get_current_hand_html(p=player_to_update),
                },
                player_pk=player_to_update.pk,
            )

        method(**kwargs)

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

        # TODO -- compare primary keys, not names
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

        just_played = legit_player
        del legit_player
        about_to_play = self.player_who_may_play

        logger.debug("%s: %s (%d) played %s", self, just_played, just_played.pk, card)

        for update_me in [just_played, about_to_play]:
            if update_me is not None:
                self.send_HTML_update_to_appropriate_channel(player_to_update=update_me)

        self.send_JSON_to_players(
            data={
                "new-play": {
                    "hand_pk": self.pk,
                    "serialized": card.serialize(),
                },
            }
        )

        self.send_HTML_to_table(
            data={
                "trick_counts_string": self.trick_counts_string(),
                "trick_html": self._get_current_trick_html(),
            }
        )

        if (final_score := self.get_xscript().final_score()) is not None:
            self.do_end_of_hand_stuff(final_score_text=str(final_score))

        return rv

    def do_end_of_hand_stuff(self, *, final_score_text: str) -> None:
        with transaction.atomic():
            assert self.is_complete
            assert self.table_display_number is not None

            for p in self.players():
                p._control_bot()

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

                self.send_HTML_to_table(
                    data={
                        "final_score": final_score_text,
                    },
                )

            if self.tournament.is_complete:
                return

    @property
    def auction(self) -> Auction:
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

        if self.auction.status is Auction.Incomplete:
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

        pbs = self.libPlayers_by_libSeat
        return Player.objects.get_by_name(pbs[seat_who_may_play].name)

    @property
    def active_seat_name(self) -> str:
        if (nsp := self.next_seat_to_play) is not None:
            return nsp.name

        return ""

    @property
    def next_seat_to_play(self) -> Seat | None:
        if not self.auction.found_contract:
            return None

        xscript = self.get_xscript()
        return xscript.next_seat_to_play()

    def modPlayer_by_seat(self, seat: Seat) -> Player:
        modelPlayer = self.players_by_direction_letter[seat.value]
        return Player.objects.get_by_name(modelPlayer.name)

    def players(self) -> models.QuerySet:
        return Player.objects.filter(pk__in=self.player_pks())

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

    @property
    def is_complete(self):
        x = self.get_xscript()

        if x.num_plays == 52:
            return True

        if x.auction.status is Auction.PassedOut:
            return True
        return False

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

    def toggle_open_access(self) -> None:
        if self.is_abandoned:
            return None

        self.open_access = not self.open_access
        self.save()
        self.send_events_to_players_and_hand(data={"open-access-status": self.open_access})

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

    # The summary is phrased in terms of the player, who is presumed to have played the board already -- except if it's
    # None, in which case we (arbitrarily) summarize in terms of North.
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


# fmt:off

# fmt:on
@admin.register(Hand)
class HandAdmin(admin.ModelAdmin):
    list_display = ["board", "open_access", "is_abandoned"]
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

        x: HandTranscript = h.get_xscript()

        rv = super().create(*args, **kwargs)

        c = libBid.deserialize(kwargs["serialized"])

        x.add_call(c)
        rv.hand._cache_set(x)

        return rv


class Call(TimeStampedModel):
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
        """Only Hand.add_play_from_player may call me; the rest of y'all should call *that*."""
        # Apparently I call this both ways :shrug:
        if "hand_id" in kwargs:
            h = Hand.objects.get(pk=kwargs["hand_id"])
        elif "hand" in kwargs:
            h = kwargs["hand"]
        else:
            msg = f"wtf: {kwargs=}"
            raise Exception(msg)

        x: HandTranscript = h.get_xscript()

        rv = super().create(*args, **kwargs)

        card = libCard.deserialize(kwargs["serialized"])

        x.add_card(card)
        rv.hand._cache_set(x)

        return rv


class Play(TimeStampedModel):
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
