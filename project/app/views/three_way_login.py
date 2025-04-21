import base64
import binascii
import logging

from django.conf import settings
from django.contrib.auth import authenticate, login
from django.http import HttpRequest, HttpResponse, JsonResponse

from app.models import Player
from app.models.utils import UserMitPlaya
from app.views import Forbid

logger = logging.getLogger(__name__)


def json_response(user: UserMitPlaya, comment: str) -> JsonResponse:
    assert user.player is not None
    data = {"player-name": user.username, "player_pk": user.player.pk, "comment": comment}

    current_hand = user.player.current_hand()
    if current_hand is not None:
        data["hand_pk"] = current_hand.pk

    return JsonResponse(data)


# Accepts ordinary usernames *and* primary keys for django.contrib.auth.models.user;
# Accepts the relevant user's password *and* the "skeleton key"
def three_way_login_view(request: HttpRequest) -> HttpResponse:
    user = getattr(request, "user", None)

    if user and user.is_authenticated:
        msg = f"{user.username} is already authenticated -- welcome"
        logger.info(msg)
        return json_response(user, msg)

    if (auth_header := request.headers.get("Authorization")) is None:
        msg = "No Authorization header attached to my request!  Begone!"
        logger.info(msg)
        return Forbid(msg)

    logger.info("Maybe the auth header has a clue")

    try:
        auth_flavor, b64_stuff = auth_header.split(" ", maxsplit=1)
    except ValueError as e:
        msg = f"Something about {e}"
        logger.info(msg)
        return Forbid(msg)

    if auth_flavor != "Basic":
        msg = f"I don't do {auth_flavor} authorization, sorry dude"
        logger.info(msg)
        return Forbid(msg)

    try:
        decoded = base64.b64decode(b64_stuff.encode()).decode()
    except binascii.Error as e:
        msg = f"{e}, sorry"
        logger.info(msg)
        return Forbid(msg)

    try:
        username_or_pk, password = decoded.split(":", maxsplit=1)
    except ValueError as e:
        msg = f"{e}, sorry"
        logger.info(msg)
        return Forbid(msg)

    if username_or_pk.isdigit():  # TODO -- this won't work if we shift to, say, UUIDs as keys
        if (player := Player.objects.filter(pk=username_or_pk).first()) is not None:
            user = player.user
            if password.rstrip() == settings.API_SKELETON_KEY:
                login(request, user)
                msg = f"Oh look, {user.username} used the skeleton key"
                logger.debug("%s", msg)
                return json_response(user, msg)

            logger.info(msg)
            return Forbid(msg)

    elif (user := authenticate(username=username_or_pk, password=password)) is None:
        msg = f"{username_or_pk=} with that password just doesn't cut it, sorry"
        logger.info(msg)
        return Forbid(msg)

    msg = f"{user=} used a regular password. Splendid."
    logger.info(msg)
    try:
        login(request, user)
    except Exception as e:
        msg = f"Bummer -- logging in {user} got us {e}"
        logger.warning(msg)
        return Forbid(msg)

    assert user is not None
    logger.debug(f"Just logged in {user.username}")
    return json_response(user, msg)
