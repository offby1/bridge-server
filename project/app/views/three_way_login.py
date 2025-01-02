import base64
import binascii
import logging

from django.conf import settings
from django.contrib.auth import authenticate, login
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden, JsonResponse
from django.utils.html import escape

from app.models import Player

logger = logging.getLogger(__name__)


# Accepts ordinary usernames *and* primary keys for django.contrib.auth.models.user;
# Accepts the relevant user's password *and* the "skeleton key"
def three_way_login_view(request: HttpRequest) -> HttpResponse:
    user = getattr(request, "user", None)

    if user and user.is_authenticated:
        msg = f"{user.username} is already authenticated -- welcome"
        logger.info(msg)
        return JsonResponse({"player-name": user.username, "comment": msg})

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
        if (player := Player.objects.filter(pk=username_or_pk).first()) is not None:
            user = player.user
            if password.rstrip() == settings.API_SKELETON_KEY:
                login(request, user)
                msg = f"Oh look, {user.username} used the skeleton key"
                logger.debug("%s", msg)
                return JsonResponse(
                    {
                        "player-name": user.username,
                        "comment": msg,
                    }
                )
            msg = f"{username_or_pk} looks like a number, but you didn't give us the skeleton key"
            logger.info(msg)
            return HttpResponseForbidden(escape(msg))

    elif (user := authenticate(username=username_or_pk, password=password)) is None:
        msg = f"{username_or_pk=} with that password just doesn't cut it, sorry"
        logger.info(msg)
        return HttpResponseForbidden(escape(msg))

    msg = f"{user=} used a regular password. Splendid."
    logger.info(msg)
    try:
        login(request, user)
    except Exception as e:
        msg = f"Bummer -- logging in {user} got us {e}"
        logger.warning(msg)
        return HttpResponseForbidden(escape(msg))

    assert user is not None
    logger.debug(f"Just logged in {user.username}")
    return JsonResponse({"player-name": user.get_username(), "comment": msg})
