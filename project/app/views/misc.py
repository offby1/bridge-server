from __future__ import annotations

import base64
import functools
import logging

import django.contrib.auth
from django.contrib import messages as django_web_messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponseForbidden, HttpResponseRedirect
from django.urls import reverse

import app.models
import app.models.utils

logger = logging.getLogger(__name__)


# See https://github.com/sbdchd/django-types?tab=readme-ov-file#httprequests-user-property
class AuthedHttpRequest(HttpRequest):
    user: app.models.utils.UserMitPlaya  # type: ignore [assignment]


# Set redirect to False for AJAX endoints.
def logged_in_as_player_required(redirect=True):
    def inner_wozzit(view_function):
        @functools.wraps(view_function)
        def non_players_piss_off(
            request: AuthedHttpRequest, *args, **kwargs
        ) -> HttpResponseRedirect | HttpResponseForbidden:
            if not redirect and not request.user.is_authenticated:
                return HttpResponseForbidden("Go away, anonymous scoundrel")

            player = app.models.Player.objects.filter(user__username=request.user.username).first()
            if player is None:
                django_web_messages.add_message(
                    request,
                    django_web_messages.INFO,
                    f"You ({request.user.username}) ain't no player, so you can't see whatever {view_function} would have shown you.",
                )
                return HttpResponseRedirect(reverse("app:home"))

            return view_function(request, *args, **kwargs)

        if redirect:
            return login_required(non_players_piss_off)

        return non_players_piss_off

    return inner_wozzit


def player_who_can_view_hand(
    request: HttpRequest, hand: app.models.Hand
) -> app.models.Player | None:
    """Allows either cookie-based auth, which is what most Django web pages use; *or* HTTP Basic Auth, which is what
    machine clients use.

    """
    logger.debug(f"{request.user=} {request.user.is_authenticated=}")
    if request.user.is_authenticated:
        player = getattr(request.user, "player", None)
        if player is not None:
            if player in hand.players_by_direction.values():
                return player

            logger.debug(f"{player=} not in {hand.players_by_direction.values()=}")

    if "HTTP_AUTHORIZATION" not in request.META:
        logger.debug("HTTP_AUTHORIZATION not present in header")
        return None

    auth = request.META["HTTP_AUTHORIZATION"].split()
    if len(auth) != 2:
        logger.debug("HTTP_AUTHORIZATION doesn't have exactly one colon; outta here")
        return None

    if auth[0].lower() != "basic":
        logger.debug("First field of HTTP_AUTHORIZATION isn't 'basic'; outta here")
        return None

    uname, passwd = base64.b64decode(auth[1]).decode("utf-8").split(":", 1)
    user = django.contrib.auth.authenticate(username=uname, password=passwd)
    if user is None:
        logger.debug("authenticating %s got us nuttin'; outta here", uname)
        return None

    if not user.is_active:
        logger.debug("User %s isn't active; outta here", user)
        return None

    player = app.models.Player.objects.filter(user=user).first()
    if player is None:
        logger.debug("No player corresponds to user %s; outta here", user)
        return None

    if player in hand.players_by_direction.values():
        return player

    return None
