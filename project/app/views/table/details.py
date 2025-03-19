from __future__ import annotations

import logging

import bridge.auction
import bridge.card
import bridge.contract
import bridge.seat
from django.conf import settings
from django.core.paginator import Paginator
import django.db.utils
from django.http import (
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseRedirect,
)
from django.contrib import messages
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import reverse
from django.views.decorators.http import require_http_methods

import app.models
from app.models.types import PK
from app.models.utils import assert_type
from app.views import Forbid, NotFound
from app.views.misc import (
    AuthedHttpRequest,
    logged_in_as_player_required,
)

logger = logging.getLogger(__name__)


def table_list_view(request) -> HttpResponse:
    table_list = app.models.Table.objects.order_by("id")

    tournament_pk = request.GET.get("tournament")
    if tournament_pk is not None:
        table_list = table_list.filter(tournament__pk=tournament_pk)

    paginator = Paginator(table_list, 15)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)
    page_title = f"Tables {page_obj.start_index()} through {page_obj.end_index()}"
    if tournament_pk is not None:
        tournament = get_object_or_404(app.models.Tournament, pk=tournament_pk)
        page_title += f" in tournament #{tournament.display_number}"

    t: app.models.Table
    for t in page_obj.object_list:
        if t.has_hand:
            t.summary_for_this_viewer = t.current_hand.summary_as_viewed_by(
                as_viewed_by=getattr(request.user, "player", None)
            )
            completed, in_progress = t.played_hands_count()
            t.played_hands_string = f"{completed}{'+' if in_progress else ''}"
        else:
            t.summary_for_this_viewer = "No hands played yet", "-"
            t.played_hands_string = "0"
    context = {
        "filtered_count": paginator.count,
        "page_obj": page_obj,
        "page_title": page_title,
        "tournament_pk": tournament_pk,
    }

    return TemplateResponse(request, "table_list.html", context=context)


def _auction_channel_for_table(table):
    return str(table.pk)


@require_http_methods(["POST"])
@logged_in_as_player_required()
def call_post_view(request: AuthedHttpRequest, hand_pk: PK) -> HttpResponse:
    hand: app.models.Hand = get_object_or_404(app.models.Hand, pk=hand_pk)

    player = request.user.player
    assert player is not None
    assert_type(player, app.models.Player)

    try:
        who_clicked = player.libraryThing()
    except app.models.PlayerException as e:
        return Forbid(e)

    if hand.player_who_may_call is None:
        return Forbid(f"Nobody is allowed to call now at hand {hand.pk}")

    from_whom = hand.player_who_may_call.libraryThing() if hand.open_access else who_clicked

    serialized_call: str = request.POST["call"]
    libCall = bridge.contract.Bid.deserialize(serialized_call)

    try:
        hand.add_call_from_player(
            player=from_whom,
            call=libCall,
        )
    except (
        app.models.table.TableException,
        app.models.hand.AuctionError,
        bridge.auction.AuctionException,
    ) as e:
        return Forbid(str(e))

    return HttpResponse()


@require_http_methods(["POST"])
@logged_in_as_player_required()
def play_post_view(request: AuthedHttpRequest, hand_pk: PK) -> HttpResponse:
    hand: app.models.Hand = get_object_or_404(app.models.Hand, pk=hand_pk)

    who_clicked = request.user.player
    assert who_clicked is not None
    assert_type(who_clicked, app.models.Player)

    if hand.player_who_may_play is None:
        return Forbid("Hey! Ain't nobody allowed to play now")

    assert who_clicked is not None

    if (
        hand.dummy is not None
        and hand.player_who_may_play.libraryThing().seat == hand.dummy.seat
        and hand.declarer is not None
        and who_clicked.libraryThing().seat == hand.declarer.seat
    ):
        pass
    elif not (hand.open_access or who_clicked == hand.player_who_may_play):
        msg = f"Hand {hand.pk} says: Hey! {who_clicked} can't play now; only {hand.player_who_may_play} can; {hand.open_access=}"
        logger.debug("%s", msg)
        return Forbid(msg)

    card = bridge.card.Card.deserialize(request.POST["card"])
    try:
        hand.add_play_from_player(player=hand.player_who_may_play.libraryThing(), card=card)
    except app.models.hand.PlayError as e:
        return Forbid(str(e))

    return HttpResponse()


# TODO -- perhaps rename this view to something like
# "OK_im_done_reviewing_the_recent_hand_now_show_me_the_current_hand", and *not* have it call "table.next_board()"
# (which has side effects).  Instead, assume that the final call or play in the hand triggers the check for "this
# tournament round is over; proceed to the next round".
@require_http_methods(["POST"])
@logged_in_as_player_required()
def new_board_view(request: AuthedHttpRequest, pk: PK) -> HttpResponse:
    def deal_with_completed_tournament():
        assert (
            table.tournament.is_complete
        ), f"Hey man why'd you call me if {table.tournament} isn't complete"
        tournament, created = (
            app.models.Tournament.objects.get_or_create_tournament_open_for_signups()
        )
        assert not tournament.is_complete
        assert tournament != table.tournament
        msg = f"{table.tournament} is complete"

        if created:
            msg += f", so created {tournament}"
        else:
            msg += f"; {tournament} is the current one"

        messages.info(request, msg)
        logger.info(msg)

        return HttpResponseRedirect(reverse("app:lobby"))

    assert request.user.player is not None
    logger.debug("%s wants the next_board on table %s", request.user.player.name, pk)

    table: app.models.Table = get_object_or_404(app.models.Table, pk=pk)

    if request.user.player.current_table_pk() != pk:
        msg = f"{request.user.player.name} may not get the next board at {table} because they ain't sittin' there ({request.user.player.current_table_pk()=} != {pk=})"
        logger.info("%s", msg)
        messages.error(request, msg)
        # Perhaps they were just playing at that table, and the tournament ended, so we ejected them.  In that case,
        # they might want to at least watch the rest of the tournament.
        return HttpResponseRedirect(
            reverse("app:table-list") + f"?tournament={table.tournament.pk}"
        )

    if table.tournament.is_complete:
        return deal_with_completed_tournament()

    # If this table already has an "active" hand, just redirect to that.
    ch = table.current_hand
    if not ch.is_complete:
        logger.debug("%s has an active hand %s, so redirecting to that", table, ch.pk)
        return HttpResponseRedirect(reverse("app:hand-detail", args=[ch.pk]))

    try:
        table.next_board()
    except app.models.hand.HandError as e:
        msg = f"{e}: dunno what's happening here tbh"
        logger.warning(msg)
        return Forbid(e)
    except app.models.table.RoundIsOver as e:
        msg = f"{e}: I guess I should move boards and players? TODO"
        messages.info(request, msg)
        logger.info(msg)

        return HttpResponseRedirect(
            reverse("app:table-list") + f"?tournament={table.tournament.pk}"
        )
    except app.models.table.NoMoreBoards as e:
        msg = f"{e}: I guess you just gotta wait for this tournament to finish"
        messages.info(request, msg)
        logger.info(msg)

        return HttpResponseRedirect(
            reverse("app:table-list") + f"?tournament={table.tournament.pk}"
        )
    except (django.db.utils.IntegrityError, app.models.table.TableException) as e:
        msg = f"{e}: I guess someone else requested the next board already, or something"
        messages.info(request, msg)
        logger.info(msg)

        return HttpResponseRedirect(reverse("app:hand-detail", args=[table.current_hand.pk]))

    logger.debug('Called "next_board" on %s', table)

    return HttpResponseRedirect(reverse("app:hand-detail", args=[table.current_hand.pk]))


@require_http_methods(["POST"])
@logged_in_as_player_required()
def set_table_tempo_view(
    request: AuthedHttpRequest,
    table_pk: PK,
) -> HttpResponse:
    logger.debug("%s %s", table_pk, request.POST)
    if settings.DEPLOYMENT_ENVIRONMENT == "production":
        return NotFound("Geez I dunno what you're talking about")

    table: app.models.Table = get_object_or_404(app.models.Table, pk=table_pk)
    payload = request.POST.get("tempo-seconds")
    if payload is None:
        return HttpResponseBadRequest("request is missing a value")
    tempo_seconds: float = float(payload)

    table.tempo_seconds = tempo_seconds
    table.save()
    response_text = f"{table=} {table.tempo_seconds=}"
    logger.debug("Returning %s", response_text)
    return HttpResponse(response_text)
