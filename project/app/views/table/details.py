from __future__ import annotations

import json
import logging

import bridge.auction
import bridge.card
import bridge.contract
import bridge.seat
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
from django.views.decorators.http import require_http_methods
from django_eventstream import send_event  # type: ignore

import app.models
from app.models.utils import assert_type
from app.views.misc import AuthedHttpRequest, logged_in_as_player_required

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


def _auction_channel_for_table(table):
    return str(table.pk)


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


def hand_summary_view(request: HttpRequest, table_pk: str) -> HttpResponse:
    table = get_object_or_404(app.models.Table, pk=table_pk)

    return HttpResponse(table.current_hand.status)


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
    if (
        h.dummy is not None
        and h.player_who_may_play.libraryThing.seat == h.dummy.seat
        and h.declarer is not None
        and whos_asking.libraryThing.seat == h.declarer.seat
    ):
        pass
    elif whos_asking != h.player_who_may_play:
        return HttpResponseForbidden(
            f"Hey! {whos_asking} can't play now; only {h.player_who_may_play} can"
        )

    card = bridge.card.Card.deserialize(request.POST["play"])
    h.add_play_from_player(player=seat.player.libraryThing, card=card)

    return HttpResponse()


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

    return HttpResponseRedirect(reverse("app:hand-detail", args=[t.current_hand.pk]))


@require_http_methods(["POST"])
@logged_in_as_player_required()
def new_board_view(_request: AuthedHttpRequest, pk: int) -> HttpResponse:
    table: app.models.Table = get_object_or_404(app.models.Table, pk=pk)
    table.next_board()

    return HttpResponseRedirect(reverse("app:table-detail", args=[pk]))
