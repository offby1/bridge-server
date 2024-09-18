from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

import bridge.auction
import bridge.card
import bridge.contract
import bridge.seat
from django.conf import settings
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.http import (
    HttpRequest,
    HttpResponse,
    HttpResponseForbidden,
    HttpResponseRedirect,
)
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.safestring import SafeString
from django.views.decorators.http import require_http_methods
from django_eventstream import send_event  # type: ignore

import app.models
from app.models.utils import assert_type

from .misc import logged_in_as_player_required

if TYPE_CHECKING:
    from app.models.table import AllFourSuitHoldings, SuitHolding

logger = logging.getLogger(__name__)


class UserMitPlaya(User):
    player: app.models.Player | None


# See https://github.com/sbdchd/django-types?tab=readme-ov-file#httprequests-user-property
class AuthedHttpRequest(HttpRequest):
    user: UserMitPlaya  # type: ignore [assignment]


def table_list_view(request):
    table_list = app.models.Table.objects.all()
    paginator = Paginator(table_list, 15)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)
    context = {
        "page_obj": page_obj,
        "total_count": app.models.Table.objects.count(),
    }

    return TemplateResponse(request, "table_list.html", context=context)


def bidding_box_buttons(
    *,
    auction: bridge.auction.Auction,
    call_post_endpoint: str,
    disabled_because_out_of_turn=False,
) -> SafeString:
    assert isinstance(auction, bridge.auction.Auction)

    legal_calls = auction.legal_calls()

    def buttonize(call: bridge.contract.Call, active=True):
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
            buttons.append(buttonize(b, active))

        row += "".join(buttons)

        row += "</div><br/>"

        rows.append(row)

    top_button_group = """<div class="btn-group">"""
    for call in (bridge.contract.Pass, bridge.contract.Double, bridge.contract.Redouble):
        active = call in legal_calls

        top_button_group += buttonize(call, active)
    top_button_group += "</div>"

    joined_rows = "\n".join(rows)
    return SafeString(f"""{top_button_group} <br/> {joined_rows}""")


def single_hand_as_four_divs(all_four: AllFourSuitHoldings, seat_pk: str) -> SafeString:
    def card_button(c: bridge.card.Card, suit_color: str) -> str:
        return f"""<button
        type="button"
        class="btn btn-primary"
        name="play" value="{c.serialize()}"
        style="--bs-btn-color: {suit_color}; --bs-btn-bg: #ccc"
        hx-post="{reverse("app:play-post", args=[seat_pk])}"
        hx-swap="none"
        >{c}</button>"""

    # Meant to look like an active button, but without any hover action.
    def card_text(c: bridge.card.Card, suit_color: str) -> str:
        return f"""<span
        class="btn btn-primary inactive-button"
        style="--bs-btn-color: {suit_color}; --bs-btn-bg: #ccc"
        >{c}</span>"""

    def single_row_divs(suit, holding: SuitHolding):
        suit_color = (
            "red" if suit in {bridge.card.Suit.HEARTS, bridge.card.Suit.DIAMONDS} else "black"
        )
        gauzy = all_four.this_hands_turn_to_play and not holding.legal_now
        cols = [
            card_button(c, suit_color) if holding.legal_now else card_text(c, suit_color)
            for c in sorted(holding.cards_of_one_suit, reverse=True)
        ]
        gauzy_style = 'style="opacity: 25%;"' if gauzy else ""
        return f"""<div class="btn-group" {gauzy_style}>{"".join(cols)}</div><br/>"""

    row_divs = []
    for suit, holding in sorted(all_four.items(), reverse=True):
        row_divs.append(single_row_divs(suit, holding) if holding else "<div>-</div>")

    return SafeString("<br>" "<div>" + "\n".join(row_divs) + "</div>")


def _auction_channel_for_table(table):
    return str(table.pk)


def _auction_context_for_table(table):
    return {
        "auction_event_source_endpoint": f"/events/table/{_auction_channel_for_table(table)}",
        "auction_partial_endpoint": reverse("app:auction-partial", args=[table.pk]),
        "show_auction_history": table.current_auction.status is bridge.auction.Auction.Incomplete,
        "table": table,
    }


def _get_pokey_buttons(
    *, skel: app.models.table.DisplaySkeleton, as_viewed_by_pk: str, table_pk: str
) -> dict[str, SafeString]:
    rv: dict[str, SafeString] = {}

    if not settings.POKEY_BOT_BUTTONS:
        return rv

    for libSeat, _ in skel.items():  # noqa
        button_value = json.dumps(
            {
                "direction": libSeat.value,
                "player_id": as_viewed_by_pk,
                "table_id": table_pk,
            },
        )

        rv[libSeat.name] = SafeString(f"""<div class="btn-group">
        <button
        type="button"
        class="btn btn-primary"
        name="who pokes me"
        value='{button_value}'
        hx-post="/yo/bot/"
        hx-swap="none"
        >POKE ME {libSeat.name}</button>
        </div>
        <br/>
        """)

    return rv


def _four_hands_context_for_table(
    request: AuthedHttpRequest, table: app.models.Table
) -> dict[str, Any]:
    assert request.user.player is not None
    skel = table.display_skeleton()

    # TODO -- figure out if the auction and play are over, in which case show 'em all

    cards_by_direction_display = {}
    libSeat: bridge.seat.Seat
    for libSeat, suitholdings in skel.items():
        if table.dummy is not None:
            assert_type(table.dummy, app.models.seat.Seat)
        is_dummy = table.dummy and libSeat == table.dummy.libraryThing
        this_seats_player = table.modPlayer_by_seat(libSeat)
        if (
            settings.POKEY_BOT_BUTTONS
            or (is_dummy and table.current_action and table.current_action.current_trick)
            or libSeat == request.user.player.seat.direction
        ):
            dem_cards_baby = single_hand_as_four_divs(
                suitholdings, seat_pk=this_seats_player.seat.pk
            )
        else:
            dem_cards_baby = SafeString(suitholdings.textual_summary)

        cards_by_direction_display[libSeat.name] = {
            "cards": dem_cards_baby,
            "player": this_seats_player,
        }

    return {
        "card_display": cards_by_direction_display,
        "four_hands_partial_endpoint": reverse("app:four-hands-partial", args=[table.pk]),
        "handaction_summary_endpoint": reverse("app:handaction-summary-view", args=[table.pk]),
        "play_event_source_endpoint": "/events/all-tables/",
        "pokey_buttons": _get_pokey_buttons(
            skel=skel, as_viewed_by_pk=request.user.player.pk, table_pk=table.pk
        ),
        "table": table,
    } | _three_by_three_trick_display_context_for_table(request, table)


def poke_de_bot(request):
    wassup = json.loads(request.POST["who pokes me"])

    send_event(
        channel="all-tables",
        event_type="message",
        data={
            "table": wassup["table_id"],
            "direction": wassup["direction"],
            "action": "pokey pokey",
        },
    )
    return HttpResponse("Pokey enough for ya??")


def _three_by_three_trick_display_context_for_table(
    request: HttpRequest,
    table: app.models.Table,
) -> dict[str, Any]:
    h = table.current_action

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


def _bidding_box_context_for_table(request, table):
    player = request.user.player  # type: ignore
    seat = getattr(player, "seat", None)
    display_bidding_box = table.current_auction.status == bridge.auction.Auction.Incomplete

    if not seat or seat.table != table:
        buttons = "No bidding box 'cuz you are not at this table"
    else:
        buttons = bidding_box_buttons(
            auction=table.current_auction,
            call_post_endpoint=reverse("app:call-post", args=[table.pk]),
            disabled_because_out_of_turn=player.name != table.current_auction.allowed_caller().name,
        )
    return {
        "bidding_box_buttons": buttons,
        "bidding_box_partial_endpoint": reverse("app:bidding-box-partial", args=[table.pk]),
        "display_bidding_box": display_bidding_box,
    }


def handaction_summary_view(request: HttpRequest, table_pk: str) -> HttpResponse:
    table = get_object_or_404(app.models.Table, pk=table_pk)

    return HttpResponse(table.current_action.status)


@logged_in_as_player_required()
def bidding_box_partial_view(request: HttpRequest, table_pk: str) -> TemplateResponse:
    table = get_object_or_404(app.models.Table, pk=table_pk)

    context = _bidding_box_context_for_table(request, table)

    return TemplateResponse(
        request,
        "auction-partial.html#bidding-box-partial",
        context=context,
    )


@logged_in_as_player_required()
def auction_partial_view(request, table_pk):
    table = get_object_or_404(app.models.Table, pk=table_pk)
    context = _auction_context_for_table(table)

    return TemplateResponse(request, "auction-partial.html#auction-partial", context=context)


@logged_in_as_player_required()
def four_hands_partial_view(request: AuthedHttpRequest, table_pk: str) -> TemplateResponse:
    table = get_object_or_404(app.models.Table, pk=table_pk)
    context = _four_hands_context_for_table(request, table)

    return TemplateResponse(
        request, "four-hands-3x3-partial.html#four-hands-3x3-partial", context=context
    )


@require_http_methods(["POST"])
@logged_in_as_player_required()
def call_post_view(request: AuthedHttpRequest, table_pk: str) -> HttpResponse:
    assert_type(request.user.player, app.models.Player)
    assert request.user is not None
    assert request.user.player is not None

    try:
        who_clicked = request.user.player.libraryThing  # type: ignore
    except app.models.PlayerException as e:
        return HttpResponseForbidden(str(e))

    table = get_object_or_404(app.models.Table, pk=table_pk)

    serialized_call: str = request.POST["call"]
    libCall = bridge.contract.Bid.deserialize(serialized_call)

    try:
        table.current_action.add_call_from_player(
            player=who_clicked,
            call=libCall,
        )
    except Exception as e:
        return HttpResponseForbidden(str(e))

    return HttpResponse()


@require_http_methods(["POST"])
@logged_in_as_player_required()
def play_post_view(request: AuthedHttpRequest, seat_pk: str) -> HttpResponse:
    seat = get_object_or_404(app.models.Seat, pk=seat_pk)
    whos_asking = request.user.player
    h = seat.table.current_action  # TODO -- check if it's our turn to play?
    if whos_asking != h.player_who_may_play:
        return HttpResponseForbidden(
            f"Hey! {whos_asking} can't play now; only {h.player_who_may_play} can"
        )

    card = bridge.card.Card.deserialize(request.POST["play"])
    h.add_play_from_player(player=seat.player.libraryThing, card=card)

    return HttpResponse()


@logged_in_as_player_required()
def table_detail_view(request: AuthedHttpRequest, pk: int) -> HttpResponse:
    table = get_object_or_404(app.models.Table, pk=pk)

    context = (
        _four_hands_context_for_table(request, table)
        | _auction_context_for_table(table)
        | _bidding_box_context_for_table(request, table)
    )

    return TemplateResponse(request, "table_detail.html", context=context)


@require_http_methods(["POST"])
@logged_in_as_player_required()
def new_table_for_two_partnerships(request, pk1, pk2):
    p1 = get_object_or_404(app.models.Player, pk=pk1)
    if p1.partner is None:
        return HttpResponseForbidden(f"Hey man {p1=} doesn't have a partner")

    p2 = get_object_or_404(app.models.Player, pk=pk2)
    if p2.partner is None:
        return HttpResponseForbidden(f"Hey man {p2=} doesn't have a partner")

    p3 = get_object_or_404(app.models.Player, pk=p1.partner.pk)
    p4 = get_object_or_404(app.models.Player, pk=p2.partner.pk)

    all_four = {p1, p2, p3, p4}
    if len(all_four) != 4:
        return HttpResponseForbidden(f"Hey man {all_four} isn't four distinct players")

    if request.user.player not in all_four:
        return HttpResponseForbidden(f"Hey man {request.user.player} isn't one of {all_four}")

    try:
        t = app.models.Table.objects.create_with_two_partnerships(p1, p2)
    except app.models.TableException as e:
        return HttpResponseForbidden(str(e))

    return HttpResponseRedirect(reverse("app:table-detail", args=[t.pk]))
