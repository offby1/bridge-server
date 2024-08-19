import json
from operator import attrgetter

from django.http import HttpResponse
from django.shortcuts import render
from django.template import loader
from django.urls import reverse
from django_eventstream import send_event

from ..models import Message, Player
from .misc import logged_in_as_player_required


def lobby(request):
    # TODO -- have the db do this for us, somehow
    lobby_players = [p for p in Player.objects.all() if not p.is_seated]

    return render(
        request,
        "lobby.html",
        context={
            "lobby": sorted(lobby_players, key=attrgetter("user.username")),
            "chat_html": loader.render_to_string(
                request=request,
                template_name="chat_html.html",
                context=dict(
                    chat_target="The Lobby",
                    messages=Message.objects.get_for_lobby().order_by("timestamp").all()[0:100],
                ),
            ),
            "chat_scripts": loader.render_to_string(
                request=request,
                template_name="chat_scripts.html",
                context=dict(
                    chat_event_source_endpoint="/events/lobby/",
                    chat_post_endpoint=reverse("app:send_lobby_message"),
                ),
            ),
        },
    )


@logged_in_as_player_required(redirect=False)
def send_lobby_message(request):
    if request.method == "POST":
        event_args = Message.create_lobby_event_args(
            from_player=Player.objects.get_from_user(request.user),
            message=json.loads(request.body)["message"],
        )
        send_event(*event_args)
    return HttpResponse()
