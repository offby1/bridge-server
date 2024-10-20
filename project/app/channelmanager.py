import logging

from django_eventstream.channelmanager import DefaultChannelManager  # type: ignore

from app.models.utils import UserMitPlaya

from . import models

logger = logging.getLogger(__name__)


class MyChannelManager(DefaultChannelManager):
    def can_read_channel(self, user: UserMitPlaya, channel: str) -> bool:
        logger.debug("self: %s, user: %s, channel: %s", self, user, channel)
        if user is not None and user.player is not None:
            # player-to-player messages are private.
            if (player_pks := models.Message.player_pks_from_channel_name(channel)) is not None:
                logger.debug(f"Returning {user.player.pk in player_pks=}")
                return user.player.pk in player_pks

            # per-hand channels can only be listened to by players playing that hand
            # TODO -- this is probably wrong, at least if that the events don't disclose the contents of the board.
            if channel.isdigit() and user.player.most_recent_seat is not None:
                logger.debug(
                    f"Returning {user.player.most_recent_seat.table.current_hand.pk == int(channel)=}"
                )
                return user.player.most_recent_seat.table.current_hand.pk == int(channel)

        if channel == "top-sekrit-board-creation-channel":
            # What, are you kidding?  It's TOP SEKRIT
            logger.debug(f"Returning false 'cuz {channel=}")
            return False

        # everything else is visible to everyone.
        logger.debug("Returning True")
        return True
