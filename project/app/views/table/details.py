from __future__ import annotations

import logging

import bridge.auction
import bridge.card
import bridge.contract
import bridge.seat
from django import forms
from django.http import HttpResponse
from django.template.response import TemplateResponse
from django.utils.html import format_html
from django.views.decorators.http import require_http_methods

import app.models
from app.views import Forbid
from app.views.misc import (
    AuthedHttpRequest,
    logged_in_as_player_required,
)

logger = logging.getLogger(__name__)


def _auction_channel_for_table(table):
    return str(table.pk)


@require_http_methods(["POST"])
@logged_in_as_player_required()
def call_post_view(request: AuthedHttpRequest) -> HttpResponse:
    preferred_type = request.get_preferred_type(["text/html", "application/json"])  # type: ignore [attr-defined]

    def _forbid(message: str) -> HttpResponse:
        return Forbid(message, content_type=preferred_type)

    if request.user.player is None:
        msg = f"You {request.user.username} are not a player"
        return _forbid(msg)

    hand = request.user.player.current_hand

    if hand is None:
        msg = f"{request.user.player.name} is not currently seated"
        return _forbid(msg)

    if request.user.player != hand.player_who_may_call:
        return _forbid(
            f"It's not {request.user.player.name}'s turn to call, but rather {hand.player_who_may_call.name}'s"
        )

    serialized_call: str = request.POST["call"]
    libCall = bridge.contract.Bid.deserialize(serialized_call)

    try:
        hand.add_call(call=libCall)
    except (
        app.models.hand.AuctionError,
        app.models.hand.HandError,
        bridge.auction.AuctionException,
    ) as e:
        return _forbid(str(e))

    return HttpResponse()


@require_http_methods(["POST"])
@logged_in_as_player_required()
def play_post_view(request: AuthedHttpRequest) -> HttpResponse:
    preferred_type = request.get_preferred_type(["text/html", "application/json"])  # type: ignore [attr-defined]

    def _forbid(message: str) -> HttpResponse:
        return Forbid(message, content_type=preferred_type)

    assert request.user.player is not None
    hand: app.models.Hand | None = request.user.player.current_hand

    if hand is None:
        msg = f"{request.user.player.name} is not currently seated"
        return _forbid(msg)

    try:
        card = bridge.card.Card.deserialize(request.POST["card"])
    except Exception as e:
        return _forbid(str(e))

    try:
        hand.add_play_from_model_player(player=request.user.player, card=card)
    except (app.models.hand.PlayError, bridge.xscript.PlayError) as e:
        return _forbid(str(e))

    return HttpResponse("<body>whatchoo lookin' at</body>")


@logged_in_as_player_required()
def sekrit_test_forms_view(
    request: AuthedHttpRequest, player: app.models.Player | None = None
) -> HttpResponse:
    if player is None:
        user = getattr(request, "user", None)
        if user is None:
            return HttpResponse(
                """
        <body>
        Happy now, anonymous user?
        </body>
    """
            )

        player = getattr(user, "player", None)
        if player is None:
            return HttpResponse(
                format_html(
                    """
        <body>
        No player -- happy now, user named ({})?
        </body>
        """,
                    user.username,
                )
            )

    # Find some hand in progress.
    hand = player.current_hand
    if hand is None:
        return HttpResponse(
            format_html(
                """
    <body>
    No current hand -- happy now, bitch ({})?
    </body>
    """,
                player.name,
            )
        )

    class WozzitForm(forms.Form):
        card = forms.CharField()

    # TODO:
    # populate the form with legitimate calls or plays
    context = dict(hand=hand, form=WozzitForm())

    return TemplateResponse(request, "sekrit-wozzit-template.html", context=context)
