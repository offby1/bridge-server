import base64
import binascii
import logging

from django.conf import settings
from django.contrib.auth import authenticate, login
from django.contrib.auth.models import User
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.utils.html import escape

logger = logging.getLogger(__name__)


def three_way_login_view(request: HttpRequest) -> HttpResponse:
    user = getattr(request, "user", None)

    if user and user.is_authenticated:
        msg = f"{user=} is authenticated -- welcome"
        logger.info(msg)
        return HttpResponse(escape(msg))

    if (auth_header := request.headers.get("Authorization")) is None:
        msg = "No Authorization header attached to my request!  Begone!"
        logger.info(msg)
        return HttpResponseForbidden(escape(msg))

    logger.info("Maybe the auth header has a clue")

    try:
        auth_flavor, b64_stuff = auth_header.split(" ", maxsplit=1)
    except ValueError as e:
        msg = f"Something about {e}"
        logger.info(msg)
        return HttpResponseForbidden(escape(msg))

    if auth_flavor != "Basic":
        msg = f"I don't do {auth_flavor} authorization, sorry dude"
        logger.info(msg)
        return HttpResponseForbidden(escape(msg))

    try:
        decoded = base64.b64decode(b64_stuff.encode()).decode()
    except binascii.Error as e:
        msg = f"{e}, sorry"
        logger.info(msg)
        return HttpResponseForbidden(escape(msg))

    try:
        username_or_pk, password = decoded.split(":", maxsplit=1)
    except ValueError as e:
        msg = f"{e}, sorry"
        logger.info(msg)
        return HttpResponseForbidden(escape(msg))

    if username_or_pk.isdigit():  # TODO -- this won't work if we shift to, say, UUIDs as keys
        if (user := User.objects.filter(pk=username_or_pk).first()) is not None:
            if password == settings.API_SKELETON_KEY:
                login(request, user)
                return HttpResponse(escape(f"Oh look, {user=} used the skeleton key"))

    elif (user := authenticate(username=username_or_pk, password=password)) is None:
        msg = f"{username_or_pk=} {password=} just doesn't cut it, sorry"
        logger.info(msg)
        return HttpResponseForbidden(escape(msg))

    msg = f"{user=} used a regular password. Splendid."
    logger.info(msg)
    login(request, user)
    return HttpResponse(escape(msg))
