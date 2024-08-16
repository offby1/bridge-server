from django_eventstream.channelmanager import DefaultChannelManager


class MyChannelManager(DefaultChannelManager):
    def can_read_channel(self, user, channel):
        print(f"can_read_channel: {self=} {user=} {channel=}")
        if user is None:
            return False

        if channel == "lobby":
            return True

        if channel.startswith("player:"):
            player_pks = channel.split(":")[1].split("_")
            player_pks = [int(pk) for pk in player_pks]
            return (
                user.pk in player_pks
            )  # here' we're assuming that a player's pk is always the same as their user pk
        return True
