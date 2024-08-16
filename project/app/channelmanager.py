from django_eventstream.channelmanager import DefaultChannelManager

from .models import player


class MyChannelManager(DefaultChannelManager):
    def can_read_channel(self, user, channel):
        if user is None:
            return False

        if channel == "lobby":
            return True

        if (player_pks := player.player_pks_from_channel_name(channel)) is not None:
            return (
                user.pk in player_pks
            )  # here' we're assuming that a player's pk is always the same as their user pk
        return True
