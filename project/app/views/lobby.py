import json

from django.http import HttpResponse, HttpResponseRedirect
from django.urls import reverse
from django_eventstream import send_event

from ..models import Message, Player
from .misc import logged_in_as_player_required


def lobby(request):
    return HttpResponseRedirect(reverse("app:players") + "?seated=False")


@logged_in_as_player_required(redirect=False)
def send_lobby_message(request):
    if request.method == "POST":
        event_args = Message.create_lobby_event_args(
            from_player=Player.objects.get_from_user(request.user),
            message=json.loads(request.body)["message"],
        )
        send_event(*event_args)
    return HttpResponse()
