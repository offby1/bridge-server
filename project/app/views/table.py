from __future__ import annotations

import logging
from typing import Optional

import bridge.auction
import bridge.card
import bridge.contract
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.safestring import SafeString
from django.views.decorators.http import require_http_methods

from app.models import Player, PlayerException, Table
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
    paginator = Paginator(table_list, 5)
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

    return SafeString(f"""{top_button_group} <br/> {"\n".join(rows)}""")


# TODO -- somehow activate the buttons *only* if it's our player's turn to play *and* if the associated card is a legal play.
def card_buttons_as_four_divs(cards: list[bridge.card.Card]) -> SafeString:
    by_suit: dict[bridge.card.Suit, list[bridge.card.Card]] = {s: [] for s in bridge.card.Suit}
    for c in cards:
        by_suit[c.suit].append(c)

    def card_button(c, color):
        return f"""<button
        type="button"
        class="btn btn-primary"
        style="--bs-btn-color: {color}; --bs-btn-bg: #ccc"
        disabled>{c}</button>"""

    def single_row_divs(suit, cards):
        color = "red" if suit in {bridge.card.Suit.HEARTS, bridge.card.Suit.DIAMONDS} else "black"
        cols = [card_button(c, color) for c in reversed(cards)]
        return f"""<div class="btn-group">{"".join(cols)}</div><br/>"""

    row_divs = [
        single_row_divs(suit, cards) if cards else "<div>-</div>"
        for suit, cards in sorted(by_suit.items(), reverse=True)
    ]

    return SafeString("<br>" + "\n".join(row_divs))


def _auction_channel_for_table(table):
    return str(table.pk)


def _auction_context_for_table(table):
    return {
        "auction_event_source_endpoint": f"/events/table/{_auction_channel_for_table(table)}",
        "auction_partial_endpoint": reverse("app:auction-partial", args=[table.pk]),
        "table": table,
    }


def _three_by_three_trick_display_context_for_table(request, table):
    return {
        "three_by_three_trick_display": {
            "rows": [
                ["", "North's card goes here", ""],
                ["West's card goes here", "", "East's card goes here"],
                ["", "South's card goes here", ""],
            ],
        },
    }


def _bidding_box_context_for_table(request, table):
    if table.current_handrecord.auction.status != bridge.auction.Auction.Incomplete:
        buttons = "No bidding box 'cuz the auction is over"
    else:
        player = request.user.player  # type: ignore
        seat = getattr(player, "seat", None)

        if not seat or seat.table != table:
            buttons = "No bidding box 'cuz you are not at this table"
        elif player.name != table.current_auction.allowed_caller().name:
            buttons = bidding_box_buttons(
                auction=table.current_auction,
                call_post_endpoint=reverse("app:call-post", args=[table.pk]),
                disabled_because_out_of_turn=True,
            )
        else:
            buttons = bidding_box_buttons(
                auction=table.current_auction,
                call_post_endpoint=reverse("app:call-post", args=[table.pk]),
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


@require_http_methods(["POST"])
@logged_in_as_player_required()
def call_post_view(request: AuthedHttpRequest, table_pk: str):
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


@logged_in_as_player_required()
def table_detail_view(request, pk):
    table = get_object_or_404(Table, pk=pk)

    # TODO -- figure out if there's a dummy, in which case show those; and figure out if the auction and play are over,
    # in which case show 'em all
    cards_by_direction_display = {}
    for seat, cards in table.dealt_cards_by_seat.items():
        dem_cards_baby = f"{len(cards)} cards"

        # TODO -- this seems redundant with "show_cards_for"
        if seat.player == request.user.player:
            dem_cards_baby = card_buttons_as_four_divs(cards)

        cards_by_direction_display[seat.named_direction] = {
            "player": seat.player,
            "cards": dem_cards_baby,
        }

    context = (
        {
            "card_display": cards_by_direction_display,
            "table": table,
        }
        | _auction_context_for_table(table)
        | _bidding_box_context_for_table(request, table)
    )

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

    t = Table.objects.create_with_two_partnerships(p1, p2)

    return HttpResponseRedirect(reverse("app:table-detail", args=[t.pk]))
