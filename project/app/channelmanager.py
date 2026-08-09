import logging

from django_eventstream.channelmanager import DefaultChannelManager  # type: ignore [import-untyped]

from app.models.types import PK_from_str
from app.models.utils import UserMitPlaya
from app.sse_channels import SSEChannels

from . import models

logger = logging.getLogger(__name__)


class MyChannelManager(DefaultChannelManager):
    def get_channels_for_request(self, request, view_kwargs):
        """Compute the channel set for the consolidated browser endpoint.

        The per-channel endpoints name their channel in the URLconf, via `channels` or
        `format-channels`; those still work, and we defer to the default behaviour for
        them. A request with no such kwarg is asking for everything this viewer needs on
        one connection, which is what `/events/all/` is for. See README.branch.md.

        We filter the result through `can_read_channel` ourselves, rather than leaving
        it to `get_events()`. A single unreadable channel makes `get_events()` raise
        `EventPermissionError` for the whole request, so an optimistic channel set would
        cost a viewer every update rather than just the one they can't have.
        """
        if {"channel", "channels", "format-channels"} & view_kwargs.keys():
            return super().get_channels_for_request(request, view_kwargs)

        player = getattr(request.user, "player", None)
        if player is None:
            return set()

        channels = {
            SSEChannels.player_html_hand(player.pk),
            SSEChannels.player_bot_checkbox(player.pk),
        }

        # The hand being viewed isn't necessarily the viewer's current one, and the chat
        # partner isn't derivable from the viewer either, so pages pass both in.
        #
        # Both are validated here rather than left to `can_read_channel`, which would
        # now deny them anyway: a parameter we can see is junk is better dropped than
        # turned into a channel name and refused, and the warning names the parameter
        # instead of the mangled channel it produced.
        if (raw_hand_pk := request.GET.get("hand")) is not None:
            try:
                channels.add(SSEChannels.table_html(PK_from_str(raw_hand_pk)))
            except (TypeError, ValueError):
                logger.warning("Ignoring unparseable hand %r in %s", raw_hand_pk, request.path)
        # A chat channel *is* `players:<pk>_<pk>` -- see Message.channel_name_from_players
        # -- and is not prefixed, whatever the URL of the old per-channel endpoint
        # suggested.
        if chat_channel := request.GET.get("chat"):
            if models.Message.player_pks_from_channel_name(chat_channel) is None:
                logger.warning("Ignoring unparseable chat %r in %s", chat_channel, request.path)
            else:
                channels.add(chat_channel)

        # `lobby`, `all-tables` and `partnerships` are deliberately absent: nothing in
        # the browser subscribes to them today. Add them here when something does.

        return {c for c in channels if self.can_read_channel(request.user, c)}

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
            # logger.warning(f"{player.name=} ({player_pks=}) => {rv=}")
            return rv

        # system-to-player HTML messages are similarly private.
        if (player_pk := models.Player.player_pk_from_event_HTML_hand_channel(channel)) is not None:
            rv = player_pk == player.pk
            # logger.warning(f"{player.name=} ({player_pk=}) => {rv=}")
            return rv

        # system-to-player JSON messages are similarly private.
        if (player_pk := models.Player.player_pk_from_event_JSON_hand_channel(channel)) is not None:
            rv = player_pk == player.pk
            # logger.warning(f"{player.name=} ({player_pk=}) => {rv=}")
            return rv

        # Bot checkbox updates are private to the player.
        if (player_pk := models.Player.player_pk_from_bot_checkbox_channel(channel)) is not None:
            rv = player_pk == player.pk
            return rv

        # "table" messages are visible to those currently playing the table, as well as those who have played it in the
        # past.
        if (hand_pk := models.Hand.hand_pk_from_event_table_html_channel(channel)) is not None:
            try:
                hand = models.Hand.objects.get(pk=hand_pk)
            except models.Hand.DoesNotExist:
                logger.info("Hand %s does not exist => False", hand_pk)
                return False

            return player.hand_at_which_we_played_board(hand.board) is not None

        # Global channels: no per-viewer content, so any logged-in player may read them.
        # Nothing publishes to `all-tables` today; it keeps its endpoint and its place
        # here so that connecting to it stays a no-op rather than an error.
        if channel in {SSEChannels.LOBBY, SSEChannels.PARTNERSHIPS, SSEChannels.ALL_TABLES}:
            return True

        # Deny by default.  This used to allow anything it didn't recognise, on the
        # grounds that there weren't any other messages.  That held while every channel
        # came from the URLconf, and stopped holding when /events/all/ began building
        # channel names from query parameters: a malformed name reached here, matched no
        # pattern above, and was allowed.  Twice.
        logger.warning("Denying unrecognised channel %r for %s", channel, player.name)
        return False
