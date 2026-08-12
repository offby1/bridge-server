"""Read-only queries, extracted from the models and views.

In the spirit of https://www.django-rapid-architecture.org/, "readers" live here
rather than on the models or in the views: each function retrieves and shapes data
and returns it, with no side effects. Views, the bot API, management commands and
tests can all call these directly.

Dependencies point one way: readers import from models, never the reverse.
"""

from __future__ import annotations

import collections
import dataclasses
from collections.abc import Iterable
from typing import TYPE_CHECKING

from app.models.utils import assert_type
from bridge.card import Card as libCard
from bridge.card import Suit as libSuit
from bridge.seat import Seat

if TYPE_CHECKING:
    import app.models


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


def get_display_skeleton(*, hand: app.models.Hand, as_dealt: bool = False) -> DisplaySkeleton:
    """A simplified representation of the hand, with all the attributes "filled in" -- about halfway between the model and the view."""
    xscript = hand.get_xscript()
    whose_turn_is_it = None

    if xscript.auction.found_contract:
        whose_turn_is_it = xscript.next_seat_to_play()

    rv = {}
    # xscript.legal_cards tells us which cards are legal for the current player.
    for seat, cards in hand.current_cards_by_seat(as_dealt=as_dealt).items():
        assert_type(seat, Seat)

        cards_by_suit = collections.defaultdict(list)
        for c in cards:
            cards_by_suit[c.suit].append(c)

        kwargs = {}

        for suit in libSuit:
            legal_now = False
            if seat == whose_turn_is_it:
                legal_now = any(
                    c in xscript.legal_cards(some_cards=list(cards)) for c in cards_by_suit[suit]
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
