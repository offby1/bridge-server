from __future__ import annotations

import base64
import binascii
import datetime
import functools
import logging
from typing import TYPE_CHECKING, Iterator


from django.contrib import messages as django_web_messages
from django.contrib.auth import authenticate
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.http import HttpRequest, HttpResponseForbidden, HttpResponseRedirect
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import SafeString

import app.models
import app.models.common
import app.models.utils
from app.views import Forbid

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser

logger = logging.getLogger(__name__)


# See https://github.com/sbdchd/django-types?tab=readme-ov-file#httprequests-user-property
class AuthedHttpRequest(HttpRequest):
    user: app.models.utils.UserMitPlaya  # type: ignore [assignment]


# https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Authorization#basic_authentication_2
def authenticate_from_basic_auth(request: AuthedHttpRequest) -> AbstractBaseUser | None:
    header = request.headers.get("Authorization")
    if header is None:
        logger.debug("No 'Authorization' header")
        return None

    basic, data = header.split(" ", maxsplit=1)
    if basic.lower() != "basic":
        logger.debug("First word isn't 'basic'")
        return None
    try:
        decoded = base64.b64decode(data).decode()
    except binascii.Error as e:
        logger.info(f"{data[0:100]=} => {e}")
        return None
    except Exception as e:
        logger.warning(f"{data[0:100]=} => {e}")
        return None
    try:
        u, p = decoded.split(":", maxsplit=1)
    except ValueError as e:
        logger.info(f"{decoded[0:100]=} => {e}")
        return None

    return authenticate(request, username=u, password=p)


def _enrich_user(user):
    if not user.is_authenticated:
        return user

    # "enrichment"
    amended_attribute_names = [
        f"player__current_hand__{a}__user" for a in app.models.common.attribute_names
    ]
    user_qs = User.objects.select_related(
        "player__current_hand__board__tournament", *amended_attribute_names
    )
    return user_qs.get(pk=user.pk)


# Set redirect to False for AJAX endoints.
def logged_in_as_player_required(*, redirect=True):
    def inner_wozzit(view_function):
        @functools.wraps(view_function)
        def non_players_piss_off(
            request: AuthedHttpRequest, *args, **kwargs
        ) -> HttpResponseRedirect | HttpResponseForbidden:
            request.user = _enrich_user(request.user)

            player = getattr(request.user, "player", None)
            if player is None:
                msg = f"You ({request.user.username}) ain't no player, so you can't see whatever \"{view_function.__name__}\" would have shown you."
                django_web_messages.add_message(
                    request,
                    django_web_messages.INFO,
                    msg,
                )
                if redirect:
                    home = reverse("app:home")
                    logger.debug(f"{player=}, and {redirect=}, so redirecting to {home=}")
                    return HttpResponseRedirect(home)
                logger.debug(f"{player=}, and {redirect=}, so returning ye olde 403")
                return Forbid("Go away, anonymous scoundrel")

            last_login_dt = player.user.last_login
            if last_login_dt is None:
                last_login_dt = datetime.datetime.min.replace(tzinfo=datetime.UTC)

            if player.last_action is None:
                last_action_dt = datetime.datetime.min.replace(tzinfo=datetime.UTC)
            else:
                last_action_dt = datetime.datetime.fromisoformat(player.last_action[0])

            if last_login_dt > last_action_dt:
                player.last_action = (last_login_dt, "logged in")
                player.save()

            return view_function(request, *args, **kwargs)

        if redirect:
            return login_required(non_players_piss_off)

        return non_players_piss_off

    return inner_wozzit


def make_tournament_filter_dropdown_list_items(
    request: HttpRequest, lookup: str
) -> Iterator[SafeString]:
    query_dict = request.GET.copy()
    query_dict.pop(lookup, None)

    yield (
        format_html(
            """<li><a class="dropdown-item" href="?{}">--all--</a></li>""",
            query_dict.urlencode(),
        )
    )

    for tournament in app.models.Tournament.objects.order_by("-display_number").all():
        query_dict[lookup] = str(tournament.display_number)

        yield (
            format_html(
                """<li><a class="dropdown-item" href="?{}">{}</a></li>""",
                query_dict.urlencode(),
                tournament,
            )
        )
