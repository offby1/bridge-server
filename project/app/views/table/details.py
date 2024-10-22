from __future__ import annotations

import json
import logging
import time

import bridge.auction
import bridge.card
import bridge.contract
import bridge.seat
from django.core.paginator import Paginator
from django.http import (
    HttpResponse,
    HttpResponseForbidden,
    HttpResponseNotFound,
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
    t: Table
    for t in page_obj.object_list:
        t.summary_for_this_viewer = t.current_hand.summary_as_viewed_by(
            as_viewed_by=getattr(request.user, "player", None)
        )
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
            "time": time.time(),
        },
    )
    return HttpResponse("Pokey enough for ya??")


@require_http_methods(["POST"])
@logged_in_as_player_required()
def call_post_view(request: AuthedHttpRequest, hand_pk: str) -> HttpResponse:
    assert_type(request.user.player, app.models.Player)
    assert request.user is not None
    assert request.user.player is not None

    hand: app.models.Hand = get_object_or_404(app.models.Hand, pk=hand_pk)

    try:
        who_clicked = request.user.player.libraryThing(hand=hand)  # type: ignore
    except app.models.PlayerException as e:
        return HttpResponseForbidden(str(e))

    if hand.player_who_may_call is None:
        return HttpResponseForbidden(f"Oddly, nobody is allowed to call now at hand {hand.pk}")

    from_whom = (
        hand.player_who_may_call.libraryThing(hand=hand) if hand.open_access else who_clicked
    )

    serialized_call: str = request.POST["call"]
    libCall = bridge.contract.Bid.deserialize(serialized_call)

    try:
        hand.add_call_from_player(
            player=from_whom,
            call=libCall,
        )
    except bridge.auction.AuctionException as e:
        return HttpResponseForbidden(str(e))

    return HttpResponse()


@require_http_methods(["POST"])
@logged_in_as_player_required()
def play_post_view(request: AuthedHttpRequest, hand_pk: str, seat_pk: str) -> HttpResponse:
    seat: app.models.Seat = get_object_or_404(app.models.Seat, pk=seat_pk)
    whos_asking = request.user.player
    h = get_object_or_404(app.models.Hand, pk=hand_pk)

    if h.player_who_may_play is None:
        return HttpResponseForbidden("Hey! Ain't nobody allowed to play now")
    assert whos_asking is not None
    if (
        h.dummy is not None
        and h.player_who_may_play.libraryThing(hand=h).seat == h.dummy.seat
        and h.declarer is not None
        and whos_asking.libraryThing(hand=h).seat == h.declarer.seat
    ):
        pass
    elif not (h.open_access or whos_asking == h.player_who_may_play):
        msg = f"Hand {h.pk} says: Hey! {whos_asking} can't play now; only {h.player_who_may_play} can; {h.open_access=}"
        logger.debug("%s", msg)
        return HttpResponseForbidden(msg)

    card = bridge.card.Card.deserialize(request.POST["play"])
    h.add_play_from_player(player=seat.player.libraryThing(hand=h), card=card)

    return HttpResponse()


@require_http_methods(["POST"])
@logged_in_as_player_required()
def new_table_for_two_partnerships(request: AuthedHttpRequest, pk1: str, pk2: str) -> HttpResponse:
    p1: app.models.Player = get_object_or_404(app.models.Player, pk=pk1)
    if p1.partner is None:
        return HttpResponseForbidden(f"Hey man {p1=} doesn't have a partner")

    p2: app.models.Player = get_object_or_404(app.models.Player, pk=pk2)
    if p2.partner is None:
        return HttpResponseForbidden(f"Hey man {p2=} doesn't have a partner")

    p3: app.models.Player = get_object_or_404(app.models.Player, pk=p1.partner.pk)
    p4: app.models.Player = get_object_or_404(app.models.Player, pk=p2.partner.pk)

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
    # If this table already has an "active" hand, just redirect to that.
    ch = table.current_hand
    if not ch.is_complete:
        logger.debug("Table %s has an active hand %s, so redirecting to that", table, ch)
        return HttpResponseRedirect(reverse("app:hand-detail", args=[ch.pk]))

    try:
        table.next_board()
    except Exception as e:
        return HttpResponseNotFound(e)

    logger.debug('Called "next_board" on table %s', table)

    return HttpResponseRedirect(reverse("app:hand-detail", args=[table.current_hand.pk]))
