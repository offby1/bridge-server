from django_eventstream.channelmanager import DefaultChannelManager

from . import models


class MyChannelManager(DefaultChannelManager):
    def can_read_channel(self, user, channel):
        if user is None:
            return False

        if channel == "lobby":
            return True

        if (player_pks := models.Message.player_pks_from_channel_name(channel)) is not None:
            player = models.Player.objects.get_from_user(user)
            return player.pk in player_pks

        return True
