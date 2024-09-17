from __future__ import annotations

import collections
import dataclasses
import logging
import random
from typing import TYPE_CHECKING

import bridge.card
from app.models import SEAT_CHOICES
from app.models.board import Board
from app.models.handaction import HandAction
from app.models.player import Player
from app.models.seat import Seat as modelSeat
from app.models.utils import assert_type
from bridge.card import Card as libCard
from bridge.card import Suit as libSuit
from bridge.seat import Seat as libSeat
from bridge.table import Hand as libHand
from bridge.table import Player as libPlayer
from bridge.table import Table as libTable
from bridge.xscript import HandTranscript
from django.contrib import admin
from django.db import models, transaction
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.html import format_html
from django_eventstream import send_event  # type: ignore

if TYPE_CHECKING:
    import bridge.seat
    from bridge.auction import Auction as libAuction


logger = logging.getLogger(__name__)


class TableException(Exception):
    pass


class TableManager(models.Manager):
    def get_nonfull(self):
        return self.annotate(num_seats=models.Count("seat")).filter(num_seats__lt=4)

    def create_with_two_partnerships(self, p1, p2, shuffle_deck=True):
        t = self.create()
        try:
            with transaction.atomic():
                for seat, player in zip(SEAT_CHOICES, (p1, p2, p1.partner, p2.partner)):
                    modelSeat.objects.create(
                        direction=seat,
                        player=player,
                        table=t,
                    )
        except Exception as e:
            raise TableException from e

        deck = libCard.deck()

        if shuffle_deck:
            random.shuffle(deck)

        b = Board.objects.create_from_deck_and_board_number(
            board_number=Board.objects.count() + 1,
            deck=deck,
        )

        HandAction.objects.create(board=b, table=t)

        send_event(
            channel="all-tables",
            event_type="message",
            data={
                "table": t.pk,
                "seats": [s.jsonable for s in t.seat_set.all()],
                "action": "just formed",
            },
        )

        return t


""" These dataclasses are here to make life easy for the table view, and to be testable.  They conveniently collect most
of the information that the view will need to display player's hands -- in fact, they collect everything *that this
model knows about*.  Stuff that we *don't* know about, but which the view does, are: who is looking at the browser, are
they human, &c

I hope they will let me greatly simplify four_hands_partial_view and _four_hands_context_for_table.
"""


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
    def our_turn_to_play(self) -> bool:
        for suit_name in ("spades", "hearts", "clubs", "diamonds"):
            holding = getattr(self, suit_name)
            print(f"{holding=}")
            if holding.legal_now:
                return True
        return False

    def from_suit(self, s: bridge.card.Suit) -> SuitHolding:
        return getattr(self, s.name().lower())


@dataclasses.dataclass
class DisplayThingy:
    holdings_by_seat: dict[libSeat, AllFourSuitHoldings]

    def __getitem__(self, seat: libSeat) -> AllFourSuitHoldings:
        assert_type(seat, libSeat)
        return self.holdings_by_seat[seat]

# What, no fields?  Well, Django supplies a primary key for us; and more importantly, it will put a "seat_set" attribute
# onto each instance.
class Table(models.Model):
    seat_set: models.Manager[modelSeat]
    handaction_set: models.Manager[HandAction]

    objects = TableManager()

    def __getitem__(self, seat: libSeat) -> libPlayer:
        modelPlayer = self.players_by_direction[seat.value]
        return modelPlayer.libraryThing

    def modPlayer_by_seat(self, seat: libSeat) -> Player:
        return Player.objects.get_by_name(self[seat].name)

    @cached_property
    def seats(self):
        return self.seat_set.select_related("player__user").all()

    def libraryThing(self):
        players = []
        for seat in self.seats:
            name = seat.player_name
            hand = self.current_action.board.cards_for_direction(seat.direction)
            players.append(
                libPlayer(seat=seat.libraryThing, name=name, hand=libHand(cards=hand)),
            )
        return libTable(players=players)

    @property
    def actions(self):
        return self.handaction_set.order_by("id")

    @property
    def current_auction(self) -> libAuction:
        return self.current_action.auction

    @property
    def current_auction_status(self) -> str:
        s = self.current_auction.status
        if s is self.current_auction.Incomplete:
            calls = self.current_auction.player_calls
            calls_description = "no calls"
            if calls:
                last = calls[-1]
                plural_suffix = "" if len(calls) == 1 else "s"
                calls_description = (
                    f"{len(calls)} call{plural_suffix}; last was {last.call} by {last.player}"
                )
            return calls_description
        return str(s)

    @cached_property
    def current_action(self) -> HandAction:
        rv = self.handaction_set.order_by("-id").first()
        assert rv is not None
        return rv

    @property
    def dealer(self):
        return self.current_board.dealer

    @property
    def declarer(self) -> modelSeat | None:
        if self.current_action.declarer is None:
            return None

        return modelSeat.objects.get(direction=self.current_action.declarer.seat.value, table=self)

    @property
    def dummy(self) -> modelSeat | None:
        if self.current_action.dummy is None:
            return None
        return modelSeat.objects.get(direction=self.current_action.dummy.seat.value, table=self)

    @cached_property
    def dealt_cards_by_seat(self) -> dict[modelSeat, list[libCard]]:
        rv: dict[modelSeat, list[libCard]] = {}
        board = self.current_board
        if board is None:
            return rv
        for s in self.seats:
            if s.player is not None:
                rv[s] = board.cards_for_direction(s.direction)

        return rv

    def display_skeleton(self) -> DisplayThingy:
        xscript = self.current_action.xscript
        whose_turn_is_it = xscript.next_player().seat

        rv = {}
        # xscript.legal_cards tells us which cards are legal for the current player.
        for mSeat, cards in self.current_cards_by_seat.items():
            seat = mSeat.libraryThing
            assert_type(seat, libSeat)

            cards_by_suit = collections.defaultdict(list)
            for c in cards:
                cards_by_suit[c.suit].append(c)

            kwargs = {}

            for suit in bridge.card.Suit:
                legal_now = False
                if seat == whose_turn_is_it:
                    legal_now = any(c in xscript.legal_cards() for c in cards_by_suit[suit])

                kwargs[suit.name().lower()] = SuitHolding(
                    cards_of_one_suit=cards_by_suit[suit],
                    legal_now=legal_now,
                )

            rv[seat] = AllFourSuitHoldings(
                **kwargs,
                textual_summary=f"{len(cards)} cards",
            )
        return DisplayThingy(holdings_by_seat=rv)

        holdings = AllFourSuitHoldings.from_current_cards_by_seat(self.current_cards_by_seat)
        return DisplayThingy(holdings_by_seat=holdings)

    @property
    def current_cards_by_seat(self) -> dict[modelSeat, set[libCard]]:
        rv = {}
        for seat, cardlist in self.dealt_cards_by_seat.items():
            assert_type(seat, modelSeat)
            assert_type(cardlist, list)

            rv[seat] = set(cardlist)

        if self.current_auction.found_contract:
            model_seats_by_lib_seats = {}
            for _index, libseat, card, _is_winner in self.current_action.annotated_plays:
                if libseat not in model_seats_by_lib_seats:
                    model_seats_by_lib_seats[libseat] = self.current_action.seat_from_libseat(
                        libseat,
                    )
                seat = model_seats_by_lib_seats[libseat]
                assert_type(seat, modelSeat)
                rv[seat].remove(card)

        return rv

    @property
    def current_board(self):
        return self.current_action.board

    @property
    def players_by_direction(self):
        return {s.direction: s.player for s in self.seats}

    @property
    def next_seat_to_play(self) -> modelSeat | None:
        if self.current_auction.found_contract:
            xscript = self.current_action.xscript
            return modelSeat.objects.get(table=self, direction=xscript.player.seat.value)

        return None

    def as_link(self):
        return format_html(
            "<a href='{}'>{}</a>",
            reverse("app:table-detail", kwargs={"pk": self.pk}),
            str(self),
        )

    def as_tuples(self):
        return [(SEAT_CHOICES[d], p) for d, p in self.players_by_direction.items()]

    def is_empty(self):
        return all(p is None for p in self.players_by_direction.values())

    def is_full(self):
        return all(p is not None for p in self.players_by_direction.values())

    def __str__(self):
        return f"Table {self.id}"


admin.site.register(Table)
