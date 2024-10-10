from django_eventstream.channelmanager import DefaultChannelManager  # type: ignore

from app.models.utils import UserMitPlaya

from . import models


class MyChannelManager(DefaultChannelManager):
    def can_read_channel(self, user: UserMitPlaya, channel: str) -> bool:
        if user is not None and user.player is not None:
            # player-to-player messages are private.
            if (player_pks := models.Message.player_pks_from_channel_name(channel)) is not None:
                return user.player.pk in player_pks

            # per-hand channels can only be listened to by players playing that hand
            if channel.isdigit() and user.player.most_recent_seat is not None:
                return user.player.most_recent_seat.table.current_hand.pk == int(channel)

        if channel == "top-sekrit-board-creation-channel":
            # What, are you kidding?  It's TOP SEKRIT
            return False

        # everything else is visible to everyone.
        return True
