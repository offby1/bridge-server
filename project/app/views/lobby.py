import json
import logging

from django.http import HttpResponse, HttpResponseRedirect
from django.urls import reverse
from django_eventstream import send_event  # type: ignore [import-untyped]

from app.models import Message, Player

from .misc import logged_in_as_player_required


logger = logging.getLogger(__name__)


def lobby(request):
    return HttpResponseRedirect(reverse("app:players") + "?seated=False")


# TODO -- I don't think anyone listens for these
@logged_in_as_player_required(redirect=False)
def send_lobby_message(request):
    if request.method == "POST":
        event_args = Message.create_lobby_event_args(
            from_player=Player.objects.get_from_user(request.user),
            message=json.loads(request.body)["message"],
        )
        send_event(*event_args)
    return HttpResponse()
