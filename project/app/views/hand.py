from __future__ import annotations

import collections
import dataclasses
from typing import Any, Iterable

import bridge.seat
import more_itertools
from bridge.auction import Auction
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse, HttpResponseNotFound, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.safestring import SafeString
from django.views.decorators.gzip import gzip_page

import app.models
from app.models.utils import assert_type
from app.views.misc import AuthedHttpRequest, logged_in_as_player_required


def hand_list_view(request: HttpRequest) -> HttpResponse:
    hand_list = (
        app.models.Hand.objects.all()
    )  # TODO -- filter to those that should be visible by request.user
    paginator = Paginator(hand_list, 15)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)
    context = {
        "page_obj": page_obj,
        "total_count": app.models.Hand.objects.count(),
    }

    return render(request, "hand_list.html", context=context)


@gzip_page
@logged_in_as_player_required()
def hand_archive_view(request: AuthedHttpRequest, pk: int) -> HttpResponse:
    h: app.models.Hand = get_object_or_404(app.models.Hand, pk=pk)

    board = h.board
    player = request.user.player

    assert player is not None

    a = h.auction
    c = a.status
    if c is Auction.Incomplete:
        return HttpResponseRedirect(reverse("app:table-detail", args=[h.table.pk]))

    if c is Auction.PassedOut:
        context = _four_hands_context_for_hand(request=request, hand=h, as_dealt=True)
        context |= {
            "score": 0,
            "vars_score": {"passed_out": 0},
            "show_auction_history": False,
        }
        return TemplateResponse(
            request,
            "table_archive.html",
            context=context,
        )

    declarer_vulnerable = a.declarer is not None and (
        board.ns_vulnerable
        and a.declarer.seat in (bridge.seat.Seat.NORTH, bridge.seat.Seat.SOUTH)
        or board.ew_vulnerable
        and a.declarer.seat in (bridge.seat.Seat.EAST, bridge.seat.Seat.WEST)
    )
    broken_down_score = h.xscript.final_score(declarer_vulnerable=declarer_vulnerable)

    if broken_down_score is None:
        return HttpResponseNotFound(
            f"The hand at {h.table} has not been completely played (only {len(h.xscript.tricks)} tricks), so there is no final score"
        )

    score_description = f"declarers got {broken_down_score.total} or I suppose you could say defenders got {-broken_down_score.total}"

    context = _four_hands_context_for_hand(request=request, hand=h, as_dealt=True)
    context |= {
        "score": score_description,
        "vars_score": vars(broken_down_score),
        "show_auction_history": True,
    }
    return TemplateResponse(
        request,
        "hand_archive.html",
        context=context,
    )


def current_cards_by_seat(
    *, hand: app.models.Hand, as_dealt: bool = False
) -> dict[bridge.seat.Seat, set[bridge.card.Card]]:
    rv = {}
    for seat, cardstring in hand.board.hand_strings_by_direction.items():
        rv[seat] = {bridge.card.Card.deserialize(c) for c in more_itertools.sliced(cardstring, 2)}

    if as_dealt:
        return rv

    if hand.auction.found_contract:
        model_seats_by_lib_seats = {}
        for _index, libseat, card, _is_winner in hand.annotated_plays:
            if libseat not in model_seats_by_lib_seats:
                model_seats_by_lib_seats[libseat] = hand.seat_from_libseat(
                    libseat,
                )
            seat = model_seats_by_lib_seats[libseat]
            assert_type(seat, bridge.seat.Seat)
            rv[seat].remove(card)

    return rv


@dataclasses.dataclass
class SuitHolding:
    """Given the state of the play, can one of these cards be played?  "Yes" if the xscript says we're the current
    player, and if all the cards_by_suit are "legal_cards" according to the xscript.

    Note that either all our cards are legal_cards, or none are.

    """

    legal_now: bool

    cards_of_one_suit: list[bridge.card.Card]


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

    def from_suit(self, s: bridge.card.Suit) -> SuitHolding:
        return getattr(self, s.name().lower())

    def items(self) -> Iterable[tuple[bridge.card.Suit, SuitHolding]]:
        for suitname, suit_value in bridge.card.Suit.__members__.items():
            holding = getattr(self, suitname.lower())
            yield (suit_value, holding)


@dataclasses.dataclass
class DisplaySkeleton:
    holdings_by_seat: dict[bridge.seat.Seat, AllFourSuitHoldings]

    def items(self) -> Iterable[tuple[bridge.seat.Seat, AllFourSuitHoldings]]:
        return self.holdings_by_seat.items()

    def __getitem__(self, seat: bridge.seat.Seat) -> AllFourSuitHoldings:
        assert_type(seat, bridge.seat.Seat)
        return self.holdings_by_seat[seat]


def display_skeleton(*, hand: app.models.Hand, as_dealt: bool = False) -> DisplaySkeleton:
    xscript = hand.xscript
    whose_turn_is_it = None

    if xscript.auction.found_contract:
        whose_turn_is_it = xscript.next_player().seat

    rv = {}
    # xscript.legal_cards tells us which cards are legal for the current player.
    for mSeat, cards in hand.current_cards_by_seat(as_dealt=as_dealt).items():
        seat = mSeat.libraryThing
        assert_type(seat, bridge.seat.Seat)

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
    return DisplaySkeleton(holdings_by_seat=rv)


def _display_and_control(
    *,
    table: app.models.Table,
    seat: bridge.seat.Seat,
    as_viewed_by: app.models.Player | None,
    as_dealt: bool,
) -> dict[str, bool]:
    assert_type(table, app.models.Table)
    assert_type(seat, bridge.seat.Seat)
    if as_viewed_by is not None:
        assert_type(as_viewed_by, app.models.Player)
    assert_type(as_dealt, bool)
    is_dummy = table.dummy and seat == table.dummy.libraryThing

    display_cards = (
        as_dealt  # hand is over and we're reviewing it
        or (
            as_viewed_by
            and as_viewed_by.most_recent_seat
            and seat.value == as_viewed_by.most_recent_seat.direction
        )  # it's our hand, duuude
        or (
            is_dummy and table.current_hand and table.current_hand.current_trick
        )  # it's dummy, and opening lead has been made
    )

    viewer_may_control_this_seat = False

    is_this_seats_turn_to_play = (
        table.current_hand.player_who_may_play is not None
        and table.current_hand.player_who_may_play.most_recent_seat is not None
        and table.current_hand.player_who_may_play.most_recent_seat.direction == seat.value
    )
    if (
        as_viewed_by is not None
        and display_cards
        and as_viewed_by.most_recent_seat is not None
        and is_this_seats_turn_to_play
    ):
        if seat.value == as_viewed_by.most_recent_seat.direction:  # it's our hand, duuude
            viewer_may_control_this_seat = not is_dummy  # declarer controls this hand, not dummy
        elif table.dummy is not None and table.declarer is not None:
            the_declarer: bridge.seat.Seat = table.declarer.libraryThing
            if (
                seat.value == table.dummy.direction
                and the_declarer.value == as_viewed_by.most_recent_seat.direction
            ):
                viewer_may_control_this_seat = True

    return {
        "display_cards": bool(display_cards),
        "viewer_may_control_this_seat": bool(viewer_may_control_this_seat),
    }


def _single_hand_as_four_divs(
    all_four: AllFourSuitHoldings, seat_pk: str, viewer_may_control_this_seat: bool
) -> SafeString:
    def card_button(c: bridge.card.Card) -> str:
        return f"""<button
        type="button"
        class="btn btn-primary"
        name="play" value="{c.serialize()}"
        style="--bs-btn-color: {c.color}; --bs-btn-bg: #ccc"
        hx-post="{reverse("app:play-post", args=[seat_pk])}"
        hx-swap="none"
        >{c}</button>"""

    # Meant to look like an active button, but without any hover action.
    def card_text(text: str, suit_color: str) -> str:
        return f"""<span
        class="btn btn-primary inactive-button"
        style="--bs-btn-color: {suit_color}; --bs-btn-bg: #ccc"
        >{text}</span>"""

    def single_row_divs(suit, holding: SuitHolding):
        gauzy = all_four.this_hands_turn_to_play and not holding.legal_now
        active = holding.legal_now and viewer_may_control_this_seat

        cols = [
            card_button(c) if active else card_text(str(c), c.color)
            for c in sorted(holding.cards_of_one_suit, reverse=True)
        ]
        if not cols:
            # placeholder
            return """<span
            class="btn btn-primary inactive-button"
            style="--bs-btn-color: black; --bs-btn-bg: #fffff"
            >&nbsp;</span>"""

        gauzy_style = 'style="opacity: 25%;"' if gauzy else ""
        return f"""<div class="btn-group" {gauzy_style}>{"".join(cols)}</div>"""

    row_divs = []
    for suit, holding in sorted(all_four.items(), reverse=True):
        row_divs.append(single_row_divs(suit, holding))

    highlight_style = (
        'style="background-color: lightgreen;"' if all_four.this_hands_turn_to_play else ""
    )
    return SafeString(f"<div {highlight_style}>" + "<br/>\n".join(row_divs) + "</div>")


def _three_by_three_trick_display_context_for_table(
    request: HttpRequest,
    table: app.models.Table,
) -> dict[str, Any]:
    h = table.current_hand

    cards_by_direction_number: dict[int, bridge.card.Card] = {}

    if h.current_trick:
        for _index, libSeat, libCard, _is_winner in h.current_trick:
            cards_by_direction_number[libSeat.value] = libCard

    def c(direction: int):
        card = cards_by_direction_number.get(direction)
        color = "black"
        if card is not None:
            # TODO -- teach the library to return a color for each card
            if card.suit in {
                bridge.card.Suit.HEARTS,
                bridge.card.Suit.DIAMONDS,
            }:
                color = "red"
        return f"""<span style="color: {color}">{card or '__'}</span>"""

    return {
        "three_by_three_trick_display": {
            "rows": [
                [" ", c(bridge.seat.Seat.NORTH.value), " "],
                [c(bridge.seat.Seat.WEST.value), " ", c(bridge.seat.Seat.EAST.value)],
                [" ", c(bridge.seat.Seat.SOUTH.value), " "],
            ],
        },
    }


def _four_hands_context_for_hand(
    *, request: AuthedHttpRequest, hand: app.models.Hand, as_dealt: bool = False
) -> dict[str, Any]:
    player = None
    if hasattr(request.user, "player"):
        player = request.user.player

    skel = hand.display_skeleton(as_dealt=as_dealt)

    cards_by_direction_display = {}
    libSeat: bridge.seat.Seat
    for libSeat, suitholdings in skel.items():
        this_seats_player = hand.modPlayer_by_seat(libSeat)
        assert this_seats_player.most_recent_seat is not None

        visibility_and_control = _display_and_control(
            hand=hand, seat=libSeat, as_viewed_by=player, as_dealt=as_dealt
        )
        if visibility_and_control["display_cards"]:
            dem_cards_baby = _single_hand_as_four_divs(
                suitholdings,
                seat_pk=this_seats_player.most_recent_seat.pk,
                viewer_may_control_this_seat=visibility_and_control["viewer_may_control_this_seat"],
            )
        else:
            dem_cards_baby = SafeString(suitholdings.textual_summary)

        cards_by_direction_display[libSeat.name] = {
            "cards": dem_cards_baby,
            "player": this_seats_player,
        }

    return {
        "card_display": cards_by_direction_display,
        "four_hands_partial_endpoint": reverse("app:four-hands-partial", args=[hand.pk]),
        "hand_summary_endpoint": reverse("app:hand-summary-view", args=[hand.pk]),
        "play_event_source_endpoint": "/events/all-tables/",
        "hand": hand,
    } | _three_by_three_trick_display_context_for_table(request, hand)
