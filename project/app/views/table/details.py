from __future__ import annotations

import logging

import bridge.auction
import bridge.card
import bridge.contract
import bridge.seat
from django import forms
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.utils.html import format_html
from django.views.decorators.http import require_http_methods

import app.models
from app.models.types import PK
from app.models.utils import assert_type
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
def call_post_view(
    request: AuthedHttpRequest, hand_pk: PK, player: app.models.Player | None = None
) -> HttpResponse:
    if player is not None:
        logger.warning("Got 'player' argument that I don't yet know how to deal with")

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
        app.models.hand.AuctionError,
        bridge.auction.AuctionException,
    ) as e:
        return Forbid(str(e))

    return HttpResponse()


@require_http_methods(["POST"])
@logged_in_as_player_required()
def play_post_view(
    request: AuthedHttpRequest, hand_pk: PK, player: app.models.Player | None = None
) -> HttpResponse:
    hand = None
    if player is not None:
        hand = player.current_hand()

    if hand is not None and str(hand.pk) != str(hand_pk):
        return Forbid(f"Get your shit together -- {hand.pk=} != {hand_pk=}")

    if hand is None:
        logger.warning("Doing slow fetch; we really shudda had our caller do this for us")
        hand = app.models.Hand.objects.get_or_404(pk=hand_pk)

    who_clicked = request.user.player
    assert who_clicked is not None
    assert_type(who_clicked, app.models.Player)

    if hand.player_who_may_play is None:
        return Forbid("Hey! Ain't nobody allowed to play now")

    assert who_clicked is not None

    if (
        hand.dummy is not None
        and hand.direction_letters_by_player[hand.player_who_may_play] == hand.dummy.seat.value
        and hand.declarer is not None
        and hand.direction_letters_by_player[who_clicked] == hand.declarer.seat.value
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

    return HttpResponse("<body>whatchoo lookin' at</body>")


@logged_in_as_player_required()
def sekrit_test_forms_view(
    request: AuthedHttpRequest, player: app.models.Player | None = None
) -> HttpResponse:
    if player is not None:
        logger.warning("Got 'player' argument that I don't yet know how to deal with")

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
    hand = player.current_hand()
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
