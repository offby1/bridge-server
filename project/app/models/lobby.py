from django.db import models
from django_eventstream import send_event


def send_lobby_message(*, from_player, message):
    obj = LobbyMessage.objects.create(
        player=from_player,
        message=message,
    )
    send_event(
        "lobby",
        "message",
        {
            "who": from_player.user.username,
            "what": message,
            "when": obj.timestamp,
        },
    )


# TODO -- maybe I can use https://github.com/fanout/django-eventstream?tab=readme-ov-file#event-storage instead
class LobbyMessage(models.Model):
    timestamp = models.DateTimeField(auto_now_add=True)
    player = models.ForeignKey("Player", on_delete=models.CASCADE)
    message = models.TextField(max_length=128)
