import logging

from django.contrib import admin
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django_eventstream import send_event

logger = logging.getLogger(__name__)


class MessageManager(models.Manager):
    def get_for_lobby(self):
        return self.filter(models.Q(lobby_recipient__isnull=False))

    def get_for_player_pair(self, p1, p2):
        return self.filter(
            models.Q(player_recipient=p1) & models.Q(from_player=p2)
            | models.Q(player_recipient=p2) & models.Q(from_player=p1),
        )


class Lobby(models.Model):
    messages_for_me = GenericRelation(
        "Message",
        related_query_name="lobby_recipient",
        content_type_field="recipient_content_type",
        object_id_field="recipient_object_id",
    )

    class Meta:
        db_table_comment = "Serves no purpose other than acting as a target for lobby messages"


_THE_LOBBY = None  # once all the models get loaded, we will set this to Lobby.objects.create()


# TODO idea -- rather than have two or more nullable foreign keys, constraining at most one to be non-null, maybe I
# should have a little inheritance hierarchy -- an abstrace Message base, and LobbyMessage and PlayerMessage inheriting
# from that.
class Message(models.Model):
    objects = MessageManager()

    timestamp = models.DateTimeField(auto_now_add=True)
    from_player = models.ForeignKey(
        "Player",
        on_delete=models.CASCADE,
        related_name="sent_message",
        null=True,
        db_comment="NULL means it came from 'the system'",
    )
    message = models.TextField(max_length=128)

    recipient_content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    recipient_object_id = models.PositiveIntegerField()
    recipient_obj = GenericForeignKey("recipient_content_type", "recipient_object_id")

    def __str__(self):
        return (
            f"At {self.timestamp}, {self.from_player} says {self.message} to {self.recipient_obj}"
        )

    @staticmethod
    def channel_name_from_player_pks(pk1: int, pk2: int) -> str:
        return "players:" + "_".join([str(pk) for pk in sorted([pk1, pk2])])

    @staticmethod
    def player_pks_from_channel_name(channel_name: str) -> set[int]:
        try:
            _, pk_underscore_string = channel_name.split(":")
            return set([int(p) for p in pk_underscore_string.split("_")])
        except Exception:
            logger.exception(channel_name)
            return None

    @classmethod
    def send_player_message(kls, *, from_player, message, recipient):
        obj = kls.objects.create(
            from_player=from_player,
            message=message,
            recipient_obj=recipient,
        )

        channel_name = kls.channel_name_from_player_pks(from_player.pk, recipient.pk)
        send_event(
            channel_name,
            "message",
            {
                "who": from_player.name,
                "what": message,
                "when": obj.timestamp,
            },
        )
        return obj

    @classmethod
    def send_lobby_message(kls, *, from_player, message):
        global _THE_LOBBY
        if _THE_LOBBY is None:
            _THE_LOBBY = Lobby.objects.create()
            logger.warning(
                f"Created {_THE_LOBBY=} so as to send {message=} from {from_player=} to it",
            )

        obj = kls.objects.create(
            from_player=from_player,
            message=message,
            recipient_obj=_THE_LOBBY,
        )

        send_event(
            "lobby",
            "message",
            {
                "who": from_player.name,
                "what": message,
                "when": obj.timestamp,
            },
        )
        return obj

    class Meta:
        indexes = [
            models.Index(fields=["recipient_content_type", "recipient_object_id"]),
        ]


admin.site.register(Message)
