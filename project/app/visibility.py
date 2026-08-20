"""Who may see which cards, and who may control which seat.

Every path that shows cards asks the functions here: the interactive hand page, the
read-only hand page, the per-seat HTML we push over SSE, and the JSON transcript the
API serves. Before this module existed, each of those wrote the rules out for itself,
and the SSE push path did not check at all -- it relied on addressing the message to
the right player and rendering whatever it was handed.

There are two questions here, at two altitudes, and it helps to keep them apart:

- `hand_access` is the coarse one, asked once per request: may this viewer load this
  hand's page at all, and do they get the interactive page or the read-only review?
- `may_see_cards` is the fine one, asked once per seat while rendering: does *this*
  seat show its cards to *this* viewer?

The coarse one is not a substitute for the fine one. A read-only page served to a
viewer entitled to nothing is not a leak; it is four columns of "13 cards".

Like `app.readers`, this module has no side effects and the dependency points one
way: it imports from models, and models never import from it.

## The rules, as the code implements them today

- If the tournament is complete, everyone sees everything, anonymous visitors
  included.
- A logged-in player who can never play in this tournament -- the signup deadline has
  passed and they did not sign up -- also sees everything. They have nothing to gain
  by peeking.
- While a tournament is running, an anonymous visitor sees nothing. Otherwise a
  player could open a second browser window, look at the hand they are playing, and
  cheat up the yin-yang.
- A player who has never sat at a hand for this board sees nothing, for the same
  reason: signing up a second username would be too easy.
- A player who has sat at a hand for this board sees their own cards always; the
  dummy's cards once the opening lead is on the table; and everything once their own
  hand is complete.
- `hand.open_access` overrides all of the above. It is a debugging switch, settable
  from the admin site, and `open_access_toggle_view` refuses to work in production.
- `as_dealt=True` means "we are reviewing a hand as it was dealt" and shows
  everything, without consulting any of the rules above. Only
  `_everything_read_only_view` passes it, and the dispatcher sends a viewer there
  only for a board that nobody will play again.

`app.readers.get_display_skeleton` deliberately holds *every* seat's cards, so a
caller that renders it must gate each seat on `may_see_cards` first.

## What is deliberately not here

`Player.controls_seat` stays on the model. It answers "whose turn is it, counting
declarer playing dummy's cards", which is a question about the run of play rather
than about who may look. `may_control_seat` below wraps it with the conditions the
views add.

`app.views.hand._bidding_box_context_for_hand` decides for itself whether to enable
the bidding box. That is a third question again -- who may *call* -- and the answer
differs during the auction, when there is no seat on turn to play.

`app.views.board.board_archive_view` still decides for itself who may load a board's
archive page. Its own TODO says the check is too strict.
"""

from __future__ import annotations

import dataclasses
import enum
import functools
from typing import TYPE_CHECKING

from app.models.common import attribute_names
from bridge.seat import Seat

if TYPE_CHECKING:
    from app.models import Board, Hand, Player


@functools.total_ordering
class CardVisibility(enum.Enum):
    """How much of a board one viewer may see. The order matters: bigger is more."""

    nothing = enum.auto()
    own_hand = enum.auto()
    dummys_hand = enum.auto()
    everything = enum.auto()

    def __lt__(self, other) -> bool:
        return self.value < other.value


def card_visibility_level(*, board: Board, viewer: Player | None) -> CardVisibility:
    """How much of `board` may `viewer` see? A `viewer` of None is the anonymous user.

    This is a property of the board and the viewer, not of any one hand: it says how
    far the viewer's entitlement reaches, and `may_see_cards` turns that into an
    answer about a particular seat at a particular hand.
    """
    if board.tournament.is_complete:
        return CardVisibility.everything

    if viewer is None:
        return CardVisibility.nothing

    if board.tournament.signup_deadline_has_passed() and viewer not in board.tournament.players():
        return CardVisibility.everything

    hand = viewer.hand_at_which_we_played_board(board)
    if hand is None:
        return CardVisibility.nothing

    if hand.is_complete:
        return CardVisibility.everything

    if hand.get_xscript().num_plays > 0:
        return CardVisibility.dummys_hand

    return CardVisibility.own_hand


def seat_of_viewer_at_hand(*, hand: Hand, viewer: Player | None) -> Seat | None:
    """Which seat does `viewer` occupy at `hand`, or None if they are not at it?

    Unlike `Player.current_direction`, this returns None for a viewer who is not at
    the hand rather than raising, because asking about a hand you are not playing is
    the ordinary case here.
    """
    if viewer is None:
        return None

    for direction_name in attribute_names:
        if getattr(hand, direction_name) == viewer:
            return Seat(direction_name[0].upper())

    return None


def _dummys_seat_once_the_lead_is_down(hand: Hand) -> Seat | None:
    """Dummy's seat at `hand`, but only after the opening lead exposes those cards.

    `hand.dummy` is set the moment the auction settles, which is a trick too early:
    between the settled auction and the opening lead, dummy's cards are still theirs
    alone.
    """
    if hand.dummy is None:
        return None
    if hand.get_xscript().num_plays == 0:
        return None
    return hand.dummy.seat


def may_see_cards(*, hand: Hand, seat: Seat, viewer: Player | None, as_dealt: bool = False) -> bool:
    """May `viewer` see the cards at `seat` of `hand`? See this module's docstring."""
    if as_dealt or hand.open_access:
        return True

    match card_visibility_level(board=hand.board, viewer=viewer):
        case CardVisibility.everything:
            return True
        case CardVisibility.nothing:
            return False

    # The viewer sat at some hand for this board, which earns them their own cards
    # here, and the dummy's once the lead is down -- but only if "here" is in fact
    # where they sat.
    viewers_seat = seat_of_viewer_at_hand(hand=hand, viewer=viewer)
    if viewers_seat is None:
        return False

    if viewers_seat == seat:
        return True

    return _dummys_seat_once_the_lead_is_down(hand) == seat


def may_control_seat(*, hand: Hand, seat: Seat, viewer: Player | None) -> bool:
    """May `viewer` call or play from `seat` of `hand`, right this second?"""
    if viewer is None or not viewer.currently_seated:
        return False

    if not may_see_cards(hand=hand, seat=seat, viewer=viewer):
        return False

    if hand.player_who_may_play is None:
        return False

    if hand.open_access and not hand.is_complete:
        return True

    return viewer.controls_seat(seat=seat, right_this_second=True)


class BoardRelationship(enum.Enum):
    """How a viewer has met a board. `board_relationship` works this out."""

    never_seen_it = enum.auto()
    currently_playing_it = enum.auto()
    already_played_it = enum.auto()


def board_relationship(*, board: Board, viewer: Player) -> tuple[BoardRelationship, Hand | None]:
    """How has `viewer` met `board`, and at which hand? The hand is None for a stranger."""
    from app.models import Hand

    hand = Hand.objects.filter(Hand.has_player(viewer), board=board).first()

    if hand is None:
        return (BoardRelationship.never_seen_it, None)

    if hand.is_complete:
        return (BoardRelationship.already_played_it, hand)

    return (BoardRelationship.currently_playing_it, hand)


class HandViewMode(enum.Enum):
    """Which of a hand's two pages a viewer gets, or neither."""

    forbidden = enum.auto()
    read_only = enum.auto()
    interactive = enum.auto()


@dataclasses.dataclass(frozen=True)
class HandAccess:
    mode: HandViewMode
    explanation: str = ""
    """Why the viewer was turned away. Empty unless `mode` is `forbidden`."""


def hand_access(*, hand: Hand, viewer: Player | None) -> HandAccess:
    """May `viewer` load `hand`'s page at all, and which of the two pages do they get?

    This is the coarse question, decided once per request before anything renders:
    serve the interactive page, serve the read-only review, or refuse. `may_see_cards`
    then decides, seat by seat, what the page that got served actually shows -- so a
    read-only page for a viewer who may see nothing is not a leak, it is four columns
    of "13 cards".

    A `viewer` of None covers both the anonymous visitor and a logged-in user with no
    Player, such as the admin account; neither may play, so neither is treated
    differently here.
    """
    board = hand.board

    if not board.will_be_played_again():
        # Every table has finished this board, or the whole tournament is over, so
        # nobody can gain by looking. Even anonymous visitors get the review page.
        return HandAccess(HandViewMode.read_only)

    if viewer is None:
        return HandAccess(
            HandViewMode.forbidden,
            "Anonymous users can view only those boards that have been fully played",
        )

    relationship, viewers_own_hand = board_relationship(board=board, viewer=viewer)

    if relationship is BoardRelationship.never_seen_it:
        return HandAccess(
            HandViewMode.forbidden,
            f"You, {viewer}, have never seen board (#{board.display_number}), so you cannot see the hand.",
        )

    if relationship is BoardRelationship.currently_playing_it:
        if hand != viewers_own_hand:
            # Same board, another table: showing it would hand them every card they
            # are about to play against.
            return HandAccess(
                HandViewMode.forbidden,
                f"You, {viewer}, are playing board #{board.display_number} at another table right now,"
                " so you cannot see this hand.",
            )
        # An abandoned hand has nothing left to play, so there is nothing to be
        # interactive about.
        if hand.is_abandoned:
            return HandAccess(HandViewMode.read_only)
        return HandAccess(HandViewMode.interactive)

    return HandAccess(HandViewMode.read_only)
