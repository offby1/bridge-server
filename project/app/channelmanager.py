from django_eventstream.channelmanager import DefaultChannelManager

from . import models


class MyChannelManager(DefaultChannelManager):
    def can_read_channel(self, user, channel):
        player = models.Player.objects.get_from_user(user)
        print(f"{self=} {player=} {channel=}")
        if user is None:
            print("False 'cuz user is None")
            return False

        if channel == "lobby":
            print("True 'cuz lobby")
            return True

        if (player_pks := models.Message.player_pks_from_channel_name(channel)) is not None:
            rv = player.pk in player_pks
            print(f"{player.pk=} in {player_pks=}? {rv=}")
            return rv

        print("True because why not")
        return True
