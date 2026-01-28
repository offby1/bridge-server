"""
SSE Channel Name Registry

Centralized channel name generation for Server-Sent Events.
This ensures consistency and makes it easy to find all channel usages.
"""


class SSEChannels:
    """Registry of all SSE channel names used in the Bridge game."""

    # Global channels (no parameters)
    LOBBY = "lobby"
    PARTNERSHIPS = "partnerships"
    ALL_TABLES = "all-tables"

    @staticmethod
    def player_html_hand(player_pk: int) -> str:
        """Player's private HTML updates (bidding box, hand display).

        Sent by: Hand.call(), Hand.play()
        Received by: interactive_hand.html
        """
        return f"player:html:hand:{player_pk}"

    @staticmethod
    def player_json(player_pk: int) -> str:
        """Player's private JSON transcripts (for bots).

        Sent by: Hand.send_JSON_to_players()
        Received by: Bot API clients via /events/player/json/{player_pk}/
        """
        return f"player:json:{player_pk}"

    @staticmethod
    def player_bot_checkbox(player_pk: int) -> str:
        """Bot checkbox state for a player.

        Sent by: Player.save() when allow_bot_to_play_for_me changes
        Received by: Navbar bot checkbox via HTMX SSE extension
        """
        return f"player:bot-checkbox:{player_pk}"

    @staticmethod
    def table_html(hand_pk: int) -> str:
        """Table-wide HTML updates (auction history, trick display).

        Sent by: Hand.call(), Hand.play()
        Received by: interactive_hand.html (all players at table)
        """
        return f"table:html:{hand_pk}"

    @staticmethod
    def chat_player_to_player(channel_name: str) -> str:
        """Encrypted peer-to-peer chat channel.

        Sent by: Chat view
        Received by: chat-partial.html
        """
        return f"chat:player-to-player:{channel_name}"


# Backward compatibility: expose as module-level functions
def player_html_hand_channel(player_pk: int) -> str:
    return SSEChannels.player_html_hand(player_pk)


def player_json_channel(player_pk: int) -> str:
    return SSEChannels.player_json(player_pk)


def player_bot_checkbox_channel(player_pk: int) -> str:
    return SSEChannels.player_bot_checkbox(player_pk)


def table_html_channel(hand_pk: int) -> str:
    return SSEChannels.table_html(hand_pk)
