import logging

from django_eventstream.channelmanager import DefaultChannelManager  # type: ignore [import-untyped]

from app.models.utils import UserMitPlaya

from . import models

logger = logging.getLogger(__name__)


class MyChannelManager(DefaultChannelManager):
    def can_read_channel(self, user: UserMitPlaya, channel: str) -> bool:
        # logger.warning(f"{user=} {channel=}")
        if user is None:
            # logger.warning("False 'cuz user is None")
            return False

        player: models.Player | None
        if isinstance(user, models.Player):
            player = user
        elif (player := getattr(user, "player", None)) is None:
            # logger.warning(f"False 'cuz {player=} is None")
            return False

        # player-to-player messages are private.
        if (player_pks := models.Message.player_pks_from_channel_name(channel)) is not None:
            rv = player.pk in player_pks
            # logger.warning(f"{player.pk=} {player_pks=} => {rv=}")
            return rv

        # system-to-player HTML messages are similarly private.
        if (player_pk := models.Player.player_pk_from_event_HTML_hand_channel(channel)) is not None:
            rv = player_pk == player.pk
            # logger.warning(f"{player.pk=} {player_pk=} => {rv=}")
            return rv

        # system-to-player JSON messages are similarly private.
        if (player_pk := models.Player.player_pk_from_event_JSON_hand_channel(channel)) is not None:
            rv = player_pk == player.pk
            # logger.warning(f"{player.pk=} {player_pk=} => {rv=}")
            return rv

        # hand messages, alas, are private.
        if (hand_pk := models.Hand.hand_pk_from_event_table_html_channel(channel)) is not None:
            try:
                hand = models.Hand.objects.get(pk=hand_pk)
            except models.Hand.DoesNotExist:
                logger.info("Hand %s does not exist => False", hand_pk)
                return False
            else:
                rv = player in hand.players()
                # logger.warning(f"{player=} in  {hand.players()=} => {rv=}")
                return rv

        if channel == "partnerships":
            return True

        # everything else is visible to everyone, although I don't think there *are* any other messages.
        # logger.warning("OK, so wtf is channel %s?", channel)
        return True
