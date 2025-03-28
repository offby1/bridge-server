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
    HttpRequest,
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
from app.models.tournament import Running
from app.models.utils import assert_type
from app.views import Forbid, NotFound
from app.views.misc import (
    AuthedHttpRequest,
    logged_in_as_player_required,
)

logger = logging.getLogger(__name__)


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

    if hand.board.tournament.play_completion_deadline_has_passed():
        return Forbid(f"{hand.board.tournament}'s play completion deadline has passed, sorry")

    if hand.player_who_may_call is None:
        return Forbid(f"Oddly, nobody is allowed to call now at hand {hand.pk}")

    from_whom = hand.player_who_may_call.libraryThing() if hand.open_access else who_clicked

    serialized_call: str = request.POST["call"]
    libCall = bridge.contract.Bid.deserialize(serialized_call)

    try:
        hand.add_call_from_player(
            player=from_whom,
            call=libCall,
        )
    except (
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


@require_http_methods(["POST"])
@logged_in_as_player_required()
def new_table_for_two_partnerships(
    request: AuthedHttpRequest, tournament_pk: str, pk1: str, pk2: str
) -> HttpResponse:
    assert request.user.player is not None

    p1: app.models.Player = get_object_or_404(app.models.Player, pk=pk1)
    if p1.partner is None:
        return Forbid(f"Hey man {p1.name} doesn't have a partner")

    p2: app.models.Player = get_object_or_404(app.models.Player, pk=pk2)
    if p2.partner is None:
        return Forbid(f"Hey man {p2.name} doesn't have a partner")

    p3: app.models.Player = get_object_or_404(app.models.Player, pk=p1.partner.pk)
    p4: app.models.Player = get_object_or_404(app.models.Player, pk=p2.partner.pk)

    all_four = {p1, p2, p3, p4}
    if len(all_four) != 4:
        return Forbid(f"Hey man {[p.name for p in all_four]} isn't four distinct players")

    if request.user.player not in all_four:
        return Forbid(
            f"Hey man {request.user.player.name} isn't one of {[p.name for p in all_four]}"
        )

    logger.debug("OK, %s is one of %s", request.user.player.name, [p.name for p in all_four])

    raise Exception("TODO")
    return Forbid("Oh whoops")
