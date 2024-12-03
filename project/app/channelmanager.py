import logging

from django_eventstream.channelmanager import DefaultChannelManager  # type: ignore [import-untyped]

from app.models.utils import UserMitPlaya

from . import models

logger = logging.getLogger(__name__)


class MyChannelManager(DefaultChannelManager):
    def can_read_channel(self, user: UserMitPlaya, channel: str) -> bool:
        if user is not None and getattr(user, "player", None) is not None:
            assert user.player is not None  # mollify mypy
            # player-to-player messages are private.
            if (player_pks := models.Message.player_pks_from_channel_name(channel)) is not None:
                return user.player.pk in player_pks

            # per-hand channels can only be listened to by players playing that hand
            # TODO -- this is probably wrong, at least if that the events don't disclose the contents of the board.
            if channel.isdigit() and user.player.current_seat is not None:
                return user.player.current_seat.table.current_hand.pk == int(channel)

        if channel == "top-sekrit-board-creation-channel":
            # What, are you kidding?  It's TOP SEKRIT
            return False

        # everything else is visible to everyone.
        return True
