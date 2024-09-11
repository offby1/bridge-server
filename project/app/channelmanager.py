from django_eventstream.channelmanager import DefaultChannelManager  # type: ignore

from . import models


class MyChannelManager(DefaultChannelManager):
    def can_read_channel(self, user, channel):
        # player-to-player messages are private.
        if (player_pks := models.Message.player_pks_from_channel_name(channel)) is not None:
            return user.player is not None and user.player.pk in player_pks

        # everything else is public.
        return True
