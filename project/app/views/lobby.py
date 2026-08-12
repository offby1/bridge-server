import json
import logging

from django.http import HttpResponse, HttpResponseRedirect
from django.urls import reverse

from app.models import Message, Player

from .misc import logged_in_as_player_required

logger = logging.getLogger(__name__)


def lobby(request):
    return HttpResponseRedirect(reverse("app:players") + "?seated=False")


# TODO -- I don't think anyone listens for these
@logged_in_as_player_required(redirect=False)
def send_lobby_message(request):
    if request.method == "POST":
        # Creating the message is enough; the app_message trigger drives the
        # broadcast (see docs/README.listen-notify.md).
        Message.create_lobby_message(
            from_player=Player.objects.get_from_user(request.user),
            message=json.loads(request.body)["message"],
        )
    return HttpResponse()
