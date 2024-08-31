from django_eventstream.channelmanager import DefaultChannelManager  # type: ignore

from . import models


class MyChannelManager(DefaultChannelManager):
    def can_read_channel(self, user, channel):
        if user is None:
            return False

        if channel == "lobby":
            return True

        # Everyone can see who's partnered with whom
        if channel == "partnerships":
            return True

        if (player_pks := models.Message.player_pks_from_channel_name(channel)) is not None:
            return user.player.pk in player_pks

        return True
