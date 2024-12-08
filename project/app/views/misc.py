from __future__ import annotations

import base64
import functools
import logging
from typing import TYPE_CHECKING

import django.contrib.auth
from django.contrib import messages as django_web_messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden, HttpResponseRedirect
from django.urls import reverse
from django.views.decorators.http import require_http_methods

import app.models
import app.models.utils

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser

logger = logging.getLogger(__name__)


@require_http_methods(["POST"])
def basic_auth_login_view(request: HttpRequest) -> HttpResponse:
    logger.debug(f"{request.user=}")

    if request.user.is_authenticated:
        return HttpResponse("Looks like you're already logged in!  Cool.")

    user = get_authenticated_user_from_request(request)

    if user is None:
        return HttpResponseForbidden("Sorry dude")

    logger.debug("OK, %r looks to be an authenticated user", user)
    login(request, user)
    return HttpResponse("I guess y'all logged in now 🤷")


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


def get_credentials_from_post_body(request: HttpRequest) -> tuple[str, str] | None:
    username = request.POST.get("username")
    if username is None:
        logger.debug("No username in POST body")
        return None
    password = request.POST.get("password")
    if password is None:
        logger.debug("No password in POST body")
        return None

    logger.debug("Found %s, %s in POST body", username, "shush it's a secret")
    return username, password


def get_credentials_from_http_headers(request: HttpRequest) -> tuple[str, str] | None:
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

    u, p = base64.b64decode(auth[1]).decode("utf-8").split(":", 1)
    return (u, p)


def get_authenticated_user_from_request(request: HttpRequest) -> AbstractBaseUser | None:
    maybe = get_credentials_from_post_body(request)
    if maybe is None:
        maybe = get_credentials_from_http_headers(request)
        if maybe is None:
            logger.debug("Nothin' in post body nor http headers")
            return None

    uname, passwd = maybe
    return django.contrib.auth.authenticate(username=uname, password=passwd)


def get_authenticated_player(request: HttpRequest) -> app.models.Player | None:
    if request.user.is_authenticated:
        player = getattr(request.user, "player", None)
        if player is not None:
            return player

        logger.debug(
            "No player associated with %s; will poke around in HTTP headers for auth info",
            request.user.get_username(),
        )

    user = get_authenticated_user_from_request(request)
    if user is None:
        logger.debug("authenticating %s got us nuttin'; outta here", request.user)
        return None

    if not user.is_active:
        logger.debug("User %s isn't active; outta here", user)
        return None

    player = app.models.Player.objects.filter(user=user).first()
    if player is None:
        logger.debug("No player corresponds to user %s; outta here", user)
        return None

    return player


def player_who_can_view_hand(
    request: HttpRequest, hand: app.models.Hand
) -> app.models.Player | None:
    """Allows either cookie-based auth, which is what most Django web pages use; *or* HTTP Basic Auth, which is what
    machine clients use.

    """
    player = get_authenticated_player(request)
    if player is None:
        return None

    if player in hand.players_by_direction.values():
        return player

    return None
