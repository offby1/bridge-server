from __future__ import annotations

import logging

from django.contrib import admin
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.db import models

from .types import PK, PK_from_str

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


_THE_LOBBY: Lobby | None = None  # singleton instance, assigned later


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

    @staticmethod
    def channel_name_from_player_pks(pk1: PK, pk2: PK) -> str:
        return "players:" + "_".join([str(pk) for pk in sorted([pk1, pk2])])

    @staticmethod
    def channel_name_from_players(p1, p2) -> str:
        return Message.channel_name_from_player_pks(p1.pk, p2.pk)

    @staticmethod
    def player_pks_from_channel_name(channel_name: str) -> set[PK] | None:
        if ":" not in channel_name:
            return None
        if "_" not in channel_name:
            return None
        try:
            _, pk_underscore_string = channel_name.split(":")
            return {PK_from_str(p) for p in pk_underscore_string.split("_")}
        except Exception:
            logger.exception(channel_name)
            return None

    @classmethod
    def create_player_message(cls, *, from_player, message, recipient) -> "Message":
        return cls._create(from_player=from_player, message=message, recipient_obj=recipient)

    @classmethod
    def create_lobby_message(cls, *, from_player, message) -> "Message":
        global _THE_LOBBY
        if _THE_LOBBY is None:
            _THE_LOBBY, created = Lobby.objects.get_or_create()

        return cls._create(from_player=from_player, message=message, recipient_obj=_THE_LOBBY)

    @classmethod
    def _create(cls, *, from_player, message, recipient_obj) -> "Message":
        # Creating the row is enough: the app_message INSERT trigger drives the SSE
        # broadcast via app.broadcast.broadcast_after_message, which derives the
        # channel and event type (CHAT vs LOBBY) from the recipient.
        if len(message) > 100:
            logger.warning(f"Truncating annoyingly-long ({len(message)} characters) message")
            message = message[0:100]

        return cls.objects.create(
            from_player=from_player,
            message=message,
            recipient_obj=recipient_obj,
        )

    class Meta:
        indexes = [
            models.Index(fields=["recipient_content_type", "recipient_object_id"]),
        ]


admin.site.register(Message)
