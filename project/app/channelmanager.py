import logging

from django_eventstream.channelmanager import DefaultChannelManager  # type: ignore [import-untyped]

from app.models.utils import UserMitPlaya

from . import models

logger = logging.getLogger(__name__)


class MyChannelManager(DefaultChannelManager):
    def can_read_channel(self, user: UserMitPlaya, channel: str) -> bool:
        if user is None:
            return False

        if isinstance(user, models.Player):
            player = user
        elif (player := getattr(user, "player", None)) is None:
            return False

        # player-to-player messages are private.
        if (player_pks := models.Message.player_pks_from_channel_name(channel)) is not None:
            return player.pk in player_pks

        # system-to-player messages are similarly private.
        if (player_pk := models.Player.player_pk_from_event_channel_name(channel)) is not None:
            return player_pk == player.pk

        # hand messages, alas, are private.
        if (hand_pk := models.Hand.hand_pk_from_event_channel_name(channel)) is not None:
            hand = models.Hand.objects.get(pk=hand_pk)
            return player in hand.players()

        if channel == "partnerships":
            return True

        # everything else is visible to everyone, although I don't think there *are* any other messages.
        logger.warning("OK, so wtf is channel %s?", channel)
        return True
