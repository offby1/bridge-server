from __future__ import annotations

from typing import TYPE_CHECKING, Any

import bridge.seat
from bridge.auction import Auction
from django.conf import settings
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse, HttpResponseNotFound, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.safestring import SafeString
from django.views.decorators.gzip import gzip_page
from django.views.decorators.http import require_http_methods

import app.models
from app.models.utils import assert_type
from app.views.misc import AuthedHttpRequest, logged_in_as_player_required

if TYPE_CHECKING:
    from app.models.hand import AllFourSuitHoldings, SuitHolding


def hand_list_view(request: HttpRequest) -> HttpResponse:
    hand_list = app.models.Hand.objects.order_by(
        "id"
    ).all()  # TODO -- filter to those that should be visible by request.user
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
def hand_archive_view(request: AuthedHttpRequest, *, pk: int) -> HttpResponse:
    h: app.models.Hand = get_object_or_404(app.models.Hand, pk=pk)

    board = h.board
    player = request.user.player

    assert player is not None

    a = h.auction
    c = a.status
    if c is Auction.Incomplete:
        return HttpResponseRedirect(reverse("app:hand-detail", args=[h.pk]))

    if c is Auction.PassedOut:
        context = _four_hands_context_for_hand(request=request, hand=h, as_dealt=True)
        context |= {
            "score": 0,
            "vars_score": {"passed_out": 0},
            "show_auction_history": False,
        }
        return TemplateResponse(
            request,
            "hand_archive.html",
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


def _display_and_control(
    *,
    hand: app.models.Hand,
    seat: bridge.seat.Seat,
    as_viewed_by: app.models.Player | None,
    as_dealt: bool,
) -> dict[str, bool]:
    assert_type(hand, app.models.Hand)
    assert_type(seat, bridge.seat.Seat)
    if as_viewed_by is not None:
        assert_type(as_viewed_by, app.models.Player)
    assert_type(as_dealt, bool)
    is_dummy = hand.dummy and seat == hand.dummy.seat

    display_cards = (
        as_dealt  # hand is over and we're reviewing it
        or hand.open_access
        or (
            as_viewed_by
            and as_viewed_by.most_recent_seat
            and seat.value == as_viewed_by.most_recent_seat.direction
        )  # it's our hand, duuude
        or (is_dummy and hand and hand.current_trick)  # it's dummy, and opening lead has been made
    )

    viewer_may_control_this_seat = hand.open_access

    is_this_seats_turn_to_play = (
        hand.player_who_may_play is not None
        and hand.player_who_may_play.most_recent_seat is not None
        and hand.player_who_may_play.most_recent_seat.direction == seat.value
    )
    if (
        as_viewed_by is not None
        and display_cards
        and as_viewed_by.most_recent_seat is not None
        and is_this_seats_turn_to_play
    ):
        if seat.value == as_viewed_by.most_recent_seat.direction:  # it's our hand, duuude
            viewer_may_control_this_seat |= not is_dummy  # declarer controls this hand, not dummy
        elif hand.dummy is not None and hand.declarer is not None:
            the_declarer: bridge.seat.Seat = hand.declarer.seat
            if (
                seat == hand.dummy.seat
                and the_declarer.value == as_viewed_by.most_recent_seat.direction
            ):
                viewer_may_control_this_seat = True

    return {
        "display_cards": bool(display_cards),
        "viewer_may_control_this_seat": bool(viewer_may_control_this_seat),
    }


def _single_hand_as_four_divs(
    *, all_four: AllFourSuitHoldings, seat_pk: str, viewer_may_control_this_seat: bool
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


def _three_by_three_trick_display_context_for_hand(
    request: HttpRequest,
    hand: app.models.Hand,
) -> dict[str, Any]:
    cards_by_direction_number: dict[int, bridge.card.Card] = {}

    if hand.current_trick:
        for _index, libSeat, libCard, _is_winner in hand.current_trick:
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
                all_four=suitholdings,
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
    } | _three_by_three_trick_display_context_for_hand(request, hand)


@logged_in_as_player_required()
def four_hands_partial_view(request: AuthedHttpRequest, table_pk: str) -> TemplateResponse:
    table = get_object_or_404(app.models.Table, pk=table_pk)
    context = _four_hands_context_for_hand(request=request, hand=table.current_hand)

    return TemplateResponse(
        request, "four-hands-3x3-partial.html#four-hands-3x3-partial", context=context
    )


@gzip_page
@logged_in_as_player_required()
def hand_detail_view(request: AuthedHttpRequest, pk: int) -> HttpResponse:
    hand = get_object_or_404(app.models.Hand, pk=pk)

    if hand.is_complete or hand.auction.status is bridge.auction.Auction.PassedOut:
        return HttpResponseRedirect(reverse("app:hand-archive", args=[hand.pk]))

    context = (
        _four_hands_context_for_hand(request=request, hand=hand)
        | _auction_context_for_hand(hand)
        | _bidding_box_context_for_hand(request, hand)
    )

    return TemplateResponse(request, "hand_detail.html", context=context)


def _auction_context_for_hand(hand) -> dict[str, Any]:
    return {
        "auction_partial_endpoint": reverse("app:auction-partial", args=[hand.pk]),
        "show_auction_history": hand.auction.status is bridge.auction.Auction.Incomplete,
        "hand": hand,
    }


def _bidding_box_context_for_hand(request, hand):
    player = request.user.player  # type: ignore
    seat = player.most_recent_seat
    display_bidding_box = hand.auction.status == bridge.auction.Auction.Incomplete

    if not seat or seat.table != hand.table:
        buttons = "No bidding box 'cuz you are not at this table"
    else:
        buttons = bidding_box_buttons(
            auction=hand.auction,
            call_post_endpoint=reverse("app:call-post", args=[hand.table.pk]),
            disabled_because_out_of_turn=(
                player.name != hand.auction.allowed_caller().name and not hand.open_access
            ),
        )
    return {
        "bidding_box_buttons": buttons,
        "bidding_box_partial_endpoint": reverse("app:bidding-box-partial", args=[hand.pk]),
        "display_bidding_box": display_bidding_box,
    }


def bidding_box_buttons(
    *,
    auction: bridge.auction.Auction,
    call_post_endpoint: str,
    disabled_because_out_of_turn=False,
) -> SafeString:
    assert isinstance(auction, bridge.auction.Auction)

    legal_calls = auction.legal_calls()

    def buttonize(*, call: bridge.contract.Call, active=True):
        class_ = "btn btn-primary"
        text = call.str_for_bidding_box()

        if disabled_because_out_of_turn:
            text = text if active else f"<s>{text}</s>"
            active = False
            class_ = "btn btn-danger"

        # All one line for ease of unit testing
        return (
            """<button type="button" """
            + """hx-include="this" """
            + f"""hx-post="{call_post_endpoint}" """
            + """hx-swap="none" """
            + f"""name="call" value="{call.serialize()}" """
            + f"""class="{class_}" {"" if active else "disabled"}>"""
            + text
            + """</button>\n"""
        )

    rows = []
    bids_by_level = [
        [
            bridge.contract.Bid(level=level, denomination=denomination)
            for denomination in [*list(bridge.card.Suit), None]
        ]
        for level in range(1, 8)
    ]

    for bids in bids_by_level:
        row = '<div class="btn-group">'

        buttons = []
        for b in bids:
            active = b in legal_calls
            buttons.append(buttonize(call=b, active=active))

        row += "".join(buttons)

        row += "</div><br/>"

        rows.append(row)

    top_button_group = """<div class="btn-group">"""
    for call in (bridge.contract.Pass, bridge.contract.Double, bridge.contract.Redouble):
        active = call in legal_calls

        top_button_group += buttonize(call=call, active=active)
    top_button_group += "</div>"

    joined_rows = "\n".join(rows)
    return SafeString(f"""{top_button_group} <br/> {joined_rows}""")


@logged_in_as_player_required()
def bidding_box_partial_view(request: HttpRequest, hand_pk: str) -> TemplateResponse:
    hand = get_object_or_404(app.models.Hand, pk=hand_pk)

    context = _bidding_box_context_for_hand(request, hand)

    return TemplateResponse(
        request,
        "auction.html",
        context=context,
    )


@logged_in_as_player_required()
def auction_partial_view(request, hand_pk):
    hand = get_object_or_404(app.models.Hand, pk=hand_pk)
    context = _auction_context_for_hand(hand)

    return TemplateResponse(request, "auction-partial.html#auction-partial", context=context)


@require_http_methods(["POST"])
@logged_in_as_player_required()
def open_access_toggle_view(request: AuthedHttpRequest, hand_pk: str) -> HttpResponse:
    if settings.DEPLOYMENT_ENVIRONMENT == "production":
        return HttpResponseNotFound("Geez I dunno what you're talking about")

    hand = get_object_or_404(app.models.Hand, pk=hand_pk)

    hand.toggle_open_access()
    return HttpResponse()
