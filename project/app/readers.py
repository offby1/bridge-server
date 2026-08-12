"""Read-only queries, extracted from the models and views.

In the spirit of https://www.django-rapid-architecture.org/, "readers" live here
rather than on the models or in the views: each function retrieves and shapes data
and returns it, with no side effects. Views, the bot API, management commands and
tests can all call these directly.

Dependencies point one way: readers import from models, never the reverse.
"""

from __future__ import annotations

import collections
import contextlib
import dataclasses
from collections.abc import Iterable
from typing import Any

import app.models
import app.models.hand
from app.models.utils import assert_type
from bridge.card import Card as libCard
from bridge.card import Suit as libSuit
from bridge.seat import Seat


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


def get_annotated_tricks(hand: app.models.Hand) -> list[dict[str, Any]]:
    """Return each completed trick of `hand`, annotated for display.

    Based on "Bridge Writing Style Guide by Richard Pavlicek.pdf" (page 5): a card
    after the first is shown as a bare rank unless it changed suit, the winning
    seat is identified, and the trick is flagged for the NS / EW side.
    """
    xscript = hand.get_xscript()

    annotated = []
    for t_index, t in enumerate(xscript.tricks):
        plays = []
        winning_seat = "?"

        for p_index, p in enumerate(t.plays):
            if p_index == 0:
                led_suit = p.card.suit
                leading_seat = p.seat

            if p.wins_the_trick:
                winning_seat = p.seat.value

            plays.append(
                {
                    "card": p.card if p_index == 0 or p.card.suit != led_suit else p.card.rank,
                    "wins_the_trick": p.wins_the_trick,
                },
            )

        annotated.append(
            {
                "seat": leading_seat.name[0],
                "number": t_index + 1,
                "plays": plays,
                "ns": winning_seat in "NS",
                "ew": winning_seat in "EW",
            }
        )

    return annotated


# The summary is phrased in terms of the player if they have seen (at least some
# of) the board already; otherwise we (arbitrarily) summarize in terms of North.
def get_hand_summary(
    *, hand: app.models.Hand, as_viewed_by: app.models.Player | None
) -> tuple[str, str | int]:
    """Return a (description, score) summary of `hand` from a viewer's perspective."""
    if as_viewed_by is None:
        if not hand.tournament.is_complete:
            return "Remind me -- who are you, again?", "-"

    if as_viewed_by is not None:
        if hand.board.what_can_they_see(
            player=as_viewed_by
        ) != hand.board.PlayerVisibility.everything and as_viewed_by.pk not in {
            p.pk for p in hand.players_by_direction_letter.values()
        }:
            return (
                f"Sorry, {as_viewed_by}, but you have not completely played board {hand.board.short_string()}, so later d00d",
                "-",
            )

    auction_status = hand.get_xscript().auction.status

    if auction_status is hand.auction.Incomplete:
        return "Auction incomplete", "-"

    if auction_status is hand.auction.PassedOut:
        return "Passed Out", 0

    total_score: int | str = "-"

    my_seat_letter = "N"

    if as_viewed_by is not None:
        if (direction := hand.direction_letters_by_player.get(as_viewed_by)) is not None:
            my_seat_letter = direction

    fs = hand.get_xscript().final_score()

    if fs is None:
        trick_summary = (
            "Tournament expired" if hand.tournament.is_complete else "still being played"
        )
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


def get_board_archive_hands(
    *, board: app.models.Board, as_viewed_by: app.models.Player | None
) -> list[app.models.Hand]:
    """Every hand played on `board`, annotated for `as_viewed_by` and ranked by score.

    Each hand is decorated with `dis_my_hand`, `summary_for_this_viewer` and
    `score_for_this_viewer`, then sorted by score descending (non-numeric last).
    """
    annotated_hands: list[app.models.Hand] = []

    h: app.models.Hand
    for h in app.models.hand.enrich(board.hand_set.all()):
        h.dis_my_hand = False
        if as_viewed_by is not None and as_viewed_by.pk in h.player_pks():
            h.dis_my_hand = True
            as_viewed_by.cache_set(board=board, hand=h)

        h.summary_for_this_viewer, h.score_for_this_viewer = get_hand_summary(
            hand=h, as_viewed_by=as_viewed_by
        )

        annotated_hands.append(h)

    def numberify_score(s: int | str) -> float:
        if isinstance(s, str):
            return float("-inf")
        return s

    return sorted(
        annotated_hands,
        key=lambda s: numberify_score(s.score_for_this_viewer),
        reverse=True,
    )


def get_hint_for_player(player: app.models.Player) -> str:
    """Suggest the call or play `player` (or the seat they control) should make."""
    hand = player.current_hand
    if hand is None:
        return f"{player} has no current hand"

    xscript = hand.get_xscript()

    if player == hand.player_who_may_call:
        call = xscript.auction.make_standard_american_call(
            pbn=xscript.endplay_deal.to_pbn(),
            vuln=xscript.endplay_vulnerability(),
        )
        return f"If I were you, I'd call {call}"

    if (seat := hand.next_seat_to_play) is not None:
        if hand.player_who_controls_seat(seat, right_this_second=True):
            card = xscript.slightly_less_dumb_play().card
            return f"If I were {hand.next_seat_to_play}, I'd play {card}"

    return f"It's not {player}'s turn to call or play"


def get_player_summary_by_name_or_pk(name_or_pk: str) -> dict[str, Any] | None:
    """Look up a player by username (preferred) or primary key.

    Returns a small JSON-friendly summary, or None if no such player exists.
    """
    player = app.models.Player.objects.filter(user__username=name_or_pk).first()
    if player is None:
        with contextlib.suppress(ValueError):
            player = app.models.Player.objects.filter(pk=name_or_pk).first()

    if player is None:
        return None

    current_hand = player.current_hand
    return {
        "pk": player.pk,
        "current_table_number": (
            current_hand.table_display_number if current_hand is not None else None
        ),
        "current_hand_pk": current_hand.pk if current_hand is not None else None,
        "name": player.name,
    }


def get_chat_disabled_explanation(
    *, sender: app.models.Player, recipient: app.models.Player
) -> str | None:
    """Explain why `sender` may not chat with `recipient`, or None if they may.

    Both players must have verified via Google OAuth. A player may always talk to
    themselves (if OAuth-verified), but neither party may be seated at a hand.
    """
    if not sender.is_oauth_verified:
        return "You must sign in with Google to use chat"
    if not recipient.is_oauth_verified:
        return f"{recipient.name} hasn't signed in with Google, so you can't chat with them"

    # You can always mumble to yourself ... if you're OAuthed.  (Otherwise you'd use my bridge server as your own
    # private cloud storage.)
    if sender == recipient:
        return None

    if recipient.current_hand_and_direction() is not None:
        return f"{recipient.name} is already seated"
    if sender.current_hand_and_direction() is not None:
        return f"You, {sender.name}, are already seated"

    return None


def get_player_direction_at_hand(*, player: app.models.Player, hand: app.models.Hand) -> str:
    """Return the capitalized seat name (e.g. 'East') `player` occupies at `hand`."""
    for direction_name in hand.direction_names:
        if getattr(hand, direction_name) == player:
            return direction_name

    assert False, f"some idiot called me for {hand} when {player.name} never played it"


def player_has_played_hand(*, player: app.models.Player, hand: app.models.Hand) -> bool:
    """Whether `player` was one of the four seats at `hand`."""
    return hand in player.hands_played.all()


def get_xscript_updates(*, hand: app.models.Hand, num_calls: int, num_plays: int) -> Any:
    """Return the calls and plays added to `hand` since the caller's known counts."""
    return hand.get_xscript().whats_new(num_calls=num_calls, num_plays=num_plays)


def get_hand_status_string(hand: app.models.Hand) -> str:
    """A one-glyph status for `hand`: complete, abandoned, or still being played."""
    if hand.is_complete:
        return "✔"
    if hand.is_abandoned:
        return "✘"
    return "…"
