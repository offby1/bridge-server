from __future__ import annotations

import json
import logging
from typing import Any

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

from app.models import Player, PlayerException, Seat, Table, TableException
from app.models.utils import assert_type

from .misc import logged_in_as_player_required

logger = logging.getLogger(__name__)


class UserMitPlaya(User):
    player: Player | None


# See https://github.com/sbdchd/django-types?tab=readme-ov-file#httprequests-user-property
class AuthedHttpRequest(HttpRequest):
    user: UserMitPlaya  # type: ignore [assignment]


def table_list_view(request):
    table_list = Table.objects.all()
    paginator = Paginator(table_list, 15)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)
    context = {
        "page_obj": page_obj,
        "total_count": Table.objects.count(),
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


def cards_as_four_divs(
    *,
    players_cards: set[bridge.card.Card],
    legal_cards: list[bridge.card.Card],
    seat: Seat,
    buttons: bool = True,
) -> SafeString:
    by_suit: dict[bridge.card.Suit, list[bridge.card.Card]] = {s: [] for s in bridge.card.Suit}
    for c in players_cards:
        by_suit[c.suit].append(c)

    play_post_endpoint = reverse("app:play-post", args=[seat.pk])

    def card_button(c: bridge.card.Card, color: str) -> str:
        disabled = " disabled" if c not in legal_cards else ""

        color_styles = (
            """style="--bs-btn-disabled-color: #ffffff85; --bs-btn-disabled-bg: #0d6efd57" """
            if disabled
            else f"""style="--bs-btn-color: {color}; --bs-btn-bg: #ccc" """
        )

        return f"""<button
        type="button"
        class="btn btn-primary"
        name="play" value="{c.serialize()}"
        {color_styles}
        hx-post="{play_post_endpoint}"
        hx-swap="none"
        {disabled}>{c}</button>"""

    def card_text(c: bridge.card.Card, color: str) -> str:
        return f"""<span
        class="btn btn-primary inactive-button"
        style="--bs-btn-color: {color}; --bs-btn-bg: #ccc"
        >{c}</span>"""

    def single_row_divs(suit, cards):
        color = "red" if suit in {bridge.card.Suit.HEARTS, bridge.card.Suit.DIAMONDS} else "black"
        cols = [
            card_button(c, color) if buttons else card_text(c, color)
            for c in sorted(cards, reverse=True)
        ]
        return f"""<div class="btn-group">{"".join(cols)}</div><br/>"""

    row_divs = [
        single_row_divs(suit, cards) if cards else "<div>-</div>"
        for suit, cards in sorted(by_suit.items(), reverse=True)
    ]

    return SafeString(
        "<br>" + "\n".join(row_divs),
    )


def _auction_channel_for_table(table):
    return str(table.pk)


def _auction_context_for_table(table):
    return {
        "auction_event_source_endpoint": f"/events/table/{_auction_channel_for_table(table)}",
        "auction_partial_endpoint": reverse("app:auction-partial", args=[table.pk]),
        "show_auction_history": table.current_auction.status is bridge.auction.Auction.Incomplete,
        "table": table,
    }


def _four_hands_context_for_table(request: AuthedHttpRequest, table: Table) -> dict[str, Any]:
    # No cards are legal to play if the auction hasn't settled.
    legal_cards = []
    if table.current_auction.found_contract:
        legal_cards = table.current_handrecord.xscript.legal_cards()

    cards_by_direction_display = {}
    pokey_buttons_by_direction = {}

    # TODO -- figure out if there's a dummy, in which case show those; and figure out if the auction and play are over,
    # in which case show 'em all

    seat: Seat
    libcards: set[bridge.card.Card]
    for seat, libcards in table.current_cards_by_seat.items():
        dem_cards_baby = f"{len(libcards)} cards"

        if settings.POKEY_BOT_BUTTONS or seat.player == request.user.player:
            dem_cards_baby = cards_as_four_divs(
                players_cards=libcards,
                legal_cards=legal_cards,
                seat=seat,
                buttons=table.current_auction.found_contract,
            )

        value = json.dumps(
            {
                "direction": seat.direction,
                "player_id": seat.player.pk,
                "table_id": seat.table.pk,
            },
        )

        if settings.POKEY_BOT_BUTTONS:
            pokey_buttons_by_direction[seat.named_direction] = (
                SafeString(f"""<div class="btn-group">
        <button
        type="button"
        class="btn btn-primary"
        name="who pokes me"
        value='{value}'
        hx-post="/yo/bot/"
        hx-swap="none"
        >POKE ME {seat.named_direction}</button>
        </div>
        <br/>
        """)
            )

        cards_by_direction_display[seat.named_direction] = {
            "cards": dem_cards_baby,
            "player": seat.player,
        }

    return {
        "card_display": cards_by_direction_display,
        "four_hands_partial_endpoint": reverse("app:four-hands-partial", args=[table.pk]),
        "play_event_source_endpoint": "/events/all-tables/",
        "pokey_buttons": pokey_buttons_by_direction,
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
    table: Table,
) -> dict[str, Any]:
    h = table.current_handrecord

    cards_by_seat: dict[Seat, list[bridge.card.Card]] = {}

    if h.current_trick:
        for card in h.current_trick:
            cards_by_seat[card[1]] = card[2].serialize()

    def c(direction):
        key = getattr(bridge.seat.Seat, direction)
        card = cards_by_seat.get(key)
        color = "black"
        if card is not None:
            # TODO -- teach the library to return a color for each card
            if bridge.card.Card.deserialize(card).suit in {
                bridge.card.Suit.HEARTS,
                bridge.card.Suit.DIAMONDS,
            }:
                color = "red"
        return f"""<span style="color: {color}">{card or '__'}</span>"""

    return {
        "three_by_three_trick_display": {
            "rows": [
                [" ", c("NORTH"), " "],
                [c("WEST"), " ", c("EAST")],
                [" ", c("SOUTH"), " "],
            ],
        },
    }


def _bidding_box_context_for_table(request, table):
    player = request.user.player  # type: ignore
    seat = getattr(player, "seat", None)

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
    }


@logged_in_as_player_required()
def bidding_box_partial_view(request: HttpRequest, table_pk: str) -> TemplateResponse:
    table = get_object_or_404(Table, pk=table_pk)

    context = _bidding_box_context_for_table(request, table)

    return TemplateResponse(
        request,
        "bidding-box-partial.html#bidding-box-partial",
        context=context,
    )


@logged_in_as_player_required()
def auction_partial_view(request, table_pk):
    table = get_object_or_404(Table, pk=table_pk)
    context = _auction_context_for_table(table)

    return TemplateResponse(request, "auction-partial.html#auction-partial", context=context)


@logged_in_as_player_required()
def four_hands_partial_view(request: AuthedHttpRequest, table_pk: str) -> TemplateResponse:
    table = get_object_or_404(Table, pk=table_pk)
    context = _four_hands_context_for_table(request, table)

    return TemplateResponse(
        request, "four-hands-3x3-partial.html#four-hands-3x3-partial", context=context
    )


@require_http_methods(["POST"])
@logged_in_as_player_required()
def call_post_view(request: AuthedHttpRequest, table_pk: str) -> HttpResponse:
    assert_type(request.user.player, Player)
    assert request.user is not None
    assert request.user.player is not None

    try:
        who_clicked = request.user.player.libraryThing  # type: ignore
    except PlayerException as e:
        return HttpResponseForbidden(str(e))

    table = get_object_or_404(Table, pk=table_pk)

    serialized_call: str = request.POST["call"]
    libCall = bridge.contract.Bid.deserialize(serialized_call)

    try:
        table.current_handrecord.add_call_from_player(
            player=who_clicked,
            call=libCall,
        )
    except Exception as e:
        return HttpResponseForbidden(str(e))

    return HttpResponse()


@require_http_methods(["POST"])
@logged_in_as_player_required()
def play_post_view(request: AuthedHttpRequest, seat_pk: str) -> HttpResponse:
    seat = get_object_or_404(Seat, pk=seat_pk)
    h = seat.table.current_handrecord  # TODO -- check if it's our turn to play?
    card = bridge.card.Card.deserialize(request.POST["play"])
    h.add_play_from_player(player=seat.player.libraryThing, card=card)

    return HttpResponse()


@logged_in_as_player_required()
def table_detail_view(request: AuthedHttpRequest, pk: int) -> HttpResponse:
    table = get_object_or_404(Table, pk=pk)
    display_bidding_box = table.current_auction.status == bridge.auction.Auction.Incomplete

    context = (
        {"display_bidding_box": display_bidding_box}
        | _four_hands_context_for_table(request, table)
        | _auction_context_for_table(table)
    )

    if display_bidding_box:
        context |= _bidding_box_context_for_table(request, table)

    return TemplateResponse(request, "table_detail.html", context=context)


@require_http_methods(["POST"])
@logged_in_as_player_required()
def new_table_for_two_partnerships(request, pk1, pk2):
    p1 = get_object_or_404(Player, pk=pk1)
    if p1.partner is None:
        return HttpResponseForbidden(f"Hey man {p1=} doesn't have a partner")

    p2 = get_object_or_404(Player, pk=pk2)
    if p2.partner is None:
        return HttpResponseForbidden(f"Hey man {p2=} doesn't have a partner")

    p3 = get_object_or_404(Player, pk=p1.partner.pk)
    p4 = get_object_or_404(Player, pk=p2.partner.pk)

    all_four = {p1, p2, p3, p4}
    if len(all_four) != 4:
        return HttpResponseForbidden(f"Hey man {all_four} isn't four distinct players")

    if request.user.player not in all_four:
        return HttpResponseForbidden(f"Hey man {request.user.player} isn't one of {all_four}")

    try:
        t = Table.objects.create_with_two_partnerships(p1, p2)
    except TableException as e:
        return HttpResponseForbidden(str(e))

    return HttpResponseRedirect(reverse("app:table-detail", args=[t.pk]))
