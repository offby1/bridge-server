import logging
from typing import Optional

from django.contrib import admin
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils.html import format_html

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


_THE_LOBBY = None  # singleton instance, assigned later


class Message(models.Model):
    objects = MessageManager()

    timestamp = models.DateTimeField(auto_now_add=True)
    from_player = models.ForeignKey(  # type: ignore
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

    def as_html(self):
        return format_html(
            """
      <div class="chat-message-row">
        <div style="display: inline; font-family: monospace;" class="chat-message-timestamp">{}</div>
        <div style="display: inline;" class="chat-message-sender-name">{}</div>
        <div style="display: inline;" class="chat-message-text">{}</div>
      </div>
        """,
            self.timestamp.isoformat(),
            self.from_player.name,
            self.message,
        )

    @staticmethod
    def channel_name_from_player_pks(pk1: int, pk2: int) -> str:
        return "players:" + "_".join([str(pk) for pk in sorted([pk1, pk2])])

    @staticmethod
    def channel_name_from_players(p1, p2) -> str:
        return Message.channel_name_from_player_pks(p1.pk, p2.pk)

    @staticmethod
    def player_pks_from_channel_name(channel_name: str) -> Optional[set[int]]:
        try:
            _, pk_underscore_string = channel_name.split(":")
            return set([int(p) for p in pk_underscore_string.split("_")])
        except Exception:
            logger.exception(channel_name)
            return None

    @classmethod
    def create_player_event_args(
        kls,
        *,
        from_player,
        message,
        recipient,
    ):
        return kls._create_event_args(
            channel_name=kls.channel_name_from_players(from_player, recipient),
            from_player=from_player,
            message=message,
            recipient_obj=recipient,
        )

    @classmethod
    def create_lobby_event_args(kls, *, from_player, message):
        global _THE_LOBBY
        if _THE_LOBBY is None:
            _THE_LOBBY, created = Lobby.objects.get_or_create()
            if created:
                logger.warning(
                    f"Created {_THE_LOBBY=} so as to send {message=} from {from_player=} to it",
                )

        return kls._create_event_args(
            channel_name="lobby",
            from_player=from_player,
            message=message,  # it's like a jungle, sometimes.  It makes me wonder how I keep from going under.
            recipient_obj=_THE_LOBBY,
        )

    @classmethod
    def _create_event_args(kls, *, channel_name, from_player, message, recipient_obj):
        if len(message) > 100:
            logger.warning(f"Truncating annoyingly-long ({len(message)} characters) message")
            message = message[0:100]

        obj = kls.objects.create(
            from_player=from_player,
            message=message,
            recipient_obj=recipient_obj,
        )

        return [
            channel_name,
            "message",
            obj.as_html(),
        ]

    class Meta:
        indexes = [
            models.Index(fields=["recipient_content_type", "recipient_object_id"]),
        ]


admin.site.register(Message)
