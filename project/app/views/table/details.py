from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

import bridge.auction
import bridge.card
import bridge.contract
import bridge.seat
from django.conf import settings
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
from app.views.misc import AuthedHttpRequest, logged_in_as_player_required

if TYPE_CHECKING:
    from app.models.table import AllFourSuitHoldings, SuitHolding

logger = logging.getLogger(__name__)


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


def _auction_channel_for_table(table):
    return str(table.pk)


def _auction_context_for_table(table):
    return {
        "auction_partial_endpoint": reverse("app:auction-partial", args=[table.pk]),
        "show_auction_history": table.current_auction.status is bridge.auction.Auction.Incomplete,
        "table": table,
    }


def _get_pokey_buttons(
    *, skel: app.models.table.DisplaySkeleton, as_viewed_by: app.models.Player | None, table_pk: str
) -> dict[str, SafeString]:
    rv: dict[str, SafeString] = {}

    if not settings.POKEY_BOT_BUTTONS or as_viewed_by is None:
        return rv

    for libSeat, _ in skel.items():  # noqa
        button_value = json.dumps(
            {
                "direction": libSeat.value,
                "player_id": as_viewed_by.pk,
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
        or settings.POKEY_BOT_BUTTONS  # we're debugging
        or (as_viewed_by and seat.value == as_viewed_by.seat.direction)  # it's our hand, duuude
        or (
            is_dummy and table.current_hand and table.current_hand.current_trick
        )  # it's dummy, and opening lead has been made
    )
    viewer_may_control_this_seat = False
    is_this_seats_turn_to_play = (
        table.current_hand.player_who_may_play
        and table.current_hand.player_who_may_play.seat.direction == seat.value
    )
    if as_viewed_by is not None and display_cards and is_this_seats_turn_to_play:
        if seat.value == as_viewed_by.seat.direction:  # it's our hand, duuude
            viewer_may_control_this_seat = not is_dummy  # declarer controls this hand, not dummy
        elif table.dummy is not None and table.declarer is not None:
            the_declarer: bridge.seat.Seat = table.declarer.libraryThing
            if (
                seat.value == table.dummy.direction
                and the_declarer.value == as_viewed_by.seat.direction
            ):
                viewer_may_control_this_seat = True

    return {
        "display_cards": bool(display_cards),
        "viewer_may_control_this_seat": bool(viewer_may_control_this_seat),
    }


def _four_hands_context_for_table(
    request: AuthedHttpRequest, table: app.models.Table, as_dealt: bool = False
) -> dict[str, Any]:
    player = None
    if hasattr(request.user, "player"):
        player = request.user.player

    skel = table.display_skeleton(as_dealt=as_dealt)

    cards_by_direction_display = {}
    libSeat: bridge.seat.Seat
    for libSeat, suitholdings in skel.items():
        this_seats_player = table.modPlayer_by_seat(libSeat)

        visibility_and_control = _display_and_control(
            table=table, seat=libSeat, as_viewed_by=player, as_dealt=as_dealt
        )
        if visibility_and_control["display_cards"]:
            dem_cards_baby = _single_hand_as_four_divs(
                suitholdings,
                seat_pk=this_seats_player.seat.pk,
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
        "four_hands_partial_endpoint": reverse("app:four-hands-partial", args=[table.pk]),
        "hand_summary_endpoint": reverse("app:hand-summary-view", args=[table.pk]),
        "play_event_source_endpoint": "/events/all-tables/",
        "pokey_buttons": _get_pokey_buttons(skel=skel, as_viewed_by=player, table_pk=table.pk)
        if not as_dealt
        else "",
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


def hand_summary_view(request: HttpRequest, table_pk: str) -> HttpResponse:
    table = get_object_or_404(app.models.Table, pk=table_pk)

    return HttpResponse(table.current_hand.status)


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
        table.current_hand.add_call_from_player(
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
    h = seat.table.current_hand
    if h.player_who_may_play is None:
        return HttpResponseForbidden("Hey! Ain't nobody allowed to play now")
    assert whos_asking is not None
    if h.player_who_may_play.libraryThing == h.dummy and whos_asking.libraryThing == h.declarer:
        pass
    elif whos_asking != h.player_who_may_play:
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


def detail_or_archive_view(request: HttpRequest, pk: int) -> HttpResponseRedirect:
    """
    Redirects to either the table detail view, if the play hasn't yet completed; or to the archive view otherwise.
    """
    table = get_object_or_404(app.models.Table, pk=pk)
    viewname = "app:table-archive" if table.hand_is_complete else "app:table-detail"

    return HttpResponseRedirect(reverse(viewname, args=[table.pk]))


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
        t = app.models.Table.objects.create_with_two_partnerships(p1, p2)  # type: ignore
    except app.models.TableException as e:
        return HttpResponseForbidden(str(e))

    return HttpResponseRedirect(reverse("app:table-detail", args=[t.pk]))
