"""
SSE Channel Name Registry

Centralized channel name generation for Server-Sent Events.
This ensures consistency and makes it easy to find all channel usages.
"""

from app.models.types import PK


class SSEChannels:
    """Registry of all SSE channel names used in the Bridge game."""

    # Global channels (no parameters)
    LOBBY = "lobby"
    PARTNERSHIPS = "partnerships"
    ALL_TABLES = "all-tables"

    @staticmethod
    def player_html_hand(player_pk: PK) -> str:
        """Player's private HTML updates (bidding box, hand display).

        Sent by: Hand.call(), Hand.play()
        Received by: interactive_hand.html
        """
        return f"player:html:hand:{player_pk}"

    @staticmethod
    def player_json(player_pk: PK) -> str:
        """Player's private JSON transcripts (for bots).

        Sent by: Hand.send_JSON_to_players()
        Received by: Bot API clients via /events/player/json/{player_pk}/
        """
        return f"player:json:{player_pk}"

    @staticmethod
    def player_bot_checkbox(player_pk: PK) -> str:
        """Bot checkbox state for a player.

        Sent by: Player.save() when allow_bot_to_play_for_me changes
        Received by: Navbar bot checkbox via HTMX SSE extension
        """
        return f"player:bot-checkbox:{player_pk}"

    @staticmethod
    def table_html(hand_pk: PK) -> str:
        """Table-wide HTML updates (auction history, trick display).

        Sent by: Hand.call(), Hand.play()
        Received by: interactive_hand.html (all players at table)
        """
        return f"table:html:{hand_pk}"

    # There is deliberately no chat helper here. A chat channel is named
    # `players:<pk>_<pk>`, built by Message.channel_name_from_player_pks, and that is
    # the only place that should know the format. This class briefly had a
    # `chat_player_to_player` that prefixed `chat:player-to-player:` -- the URL path of
    # the old per-channel endpoint, not the channel name -- which nothing published to.


# Backward compatibility: expose as module-level functions
def player_html_hand_channel(player_pk: PK) -> str:
    return SSEChannels.player_html_hand(player_pk)


def player_json_channel(player_pk: PK) -> str:
    return SSEChannels.player_json(player_pk)


def player_bot_checkbox_channel(player_pk: PK) -> str:
    return SSEChannels.player_bot_checkbox(player_pk)


def table_html_channel(hand_pk: PK) -> str:
    return SSEChannels.table_html(hand_pk)
