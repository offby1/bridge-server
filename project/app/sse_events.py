"""
SSE Event Contracts for Bridge Game

This module defines the structure of all Server-Sent Events (SSE)
used in the Bridge game. Use these dataclasses to ensure consistent
event shapes across the application.
"""

from dataclasses import dataclass
from typing import Optional


class SSEEventTypes:
    """The `event:` name each kind of update travels under.

    Every event used to travel as `"message"`. On the browser's channels that worked
    only because each channel had its own connection, so the channel implied the
    meaning; we are consolidating those onto a single connection (see README.branch.md),
    where it no longer holds. htmx's `sse-swap` and our JS listeners subscribe by event
    name, so each kind of update needs a name of its own.

    The JSON stream keeps its own connection and did not have to change. We renamed its
    events anyway, because it carried four unrelated payloads under one name and clients
    had to sniff dictionary keys to tell them apart. There are no third-party clients
    yet, so this is the last cheap moment to fix that.

    Client-side subscribers, which must agree with these:
      PLAYER_HAND   `bridge-game.js`, playerEventSource
      TABLE         `bridge-game.js`, handEventSource; `read-only_hand.html`
      BOT_CHECKBOX  `base.html`, via sse-swap
      CHAT          `chat-partial.html`, via sse-swap
      PARTNERSHIPS  no subscriber today
      LOBBY         no subscriber today (see the TODO in `views/lobby.py`)
      BOT_*         no subscriber today; the reference client will be the first
    """

    # Browser channels.
    PLAYER_HAND = "player-hand"
    TABLE = "table"
    BOT_CHECKBOX = "bot-checkbox"
    CHAT = "chat"
    PARTNERSHIPS = "partnerships"
    LOBBY = "lobby"

    # The JSON stream at /events/player/json/{player_pk}/, one name per payload.
    BOT_SETTING = "bot-setting"
    BOT_NEW_CALL = "new-call"
    BOT_NEW_PLAY = "new-play"
    BOT_CONTRACT = "contract"


@dataclass
class PlayerHandEvent:
    """Events sent to individual players about their hand state.

    Channel: /events/player/html/hand/{player_pk}/
    """

    bidding_box_html: Optional[str] = None
    current_hand_html: Optional[str] = None
    current_hand_direction: Optional[str] = None  # "north", "south", etc.
    tempo_seconds: Optional[float] = None
    hand_pk: Optional[int] = None
    show_hint_button: Optional[bool] = None

    def to_dict(self):
        """Return only non-None fields (without deep copying)"""
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class TableEvent:
    """Events sent to all players at a table.

    Channel: /events/table/html/{hand_pk}/
    """

    auction_history_html: Optional[str] = None
    trick_html: Optional[str] = None
    trick_counts_string: Optional[str] = None
    contract_text: Optional[str] = None  # Triggers reload
    final_score: Optional[dict] = None  # Triggers reload
    play_completion_deadline: Optional[str] = None  # Triggers reload

    def to_dict(self):
        """Return only non-None fields (without deep copying)"""
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class BotCheckboxEvent:
    """Bot checkbox state update.

    Channel: /events/player/bot-checkbox/{player_pk}/
    """

    html: str  # Rendered bot-checkbox.html


@dataclass
class BotAPIEvent:
    """JSON events for bot API clients.

    Channel: /events/player/json/{player_pk}/
    """

    allow_bot_to_play_for_me: Optional[bool] = None
    hand_pk: Optional[int] = None
    new_call: Optional[dict] = None  # {"serialized": "1♣"}
    new_play: Optional[dict] = None  # {"serialized": "♠A"}
    tempo_seconds: Optional[float] = None

    def to_dict(self):
        """Return only non-None fields (without deep copying)"""
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class LobbyEvent:
    """Lobby chat messages.

    Channel: /events/lobby/
    """

    message: str
    from_player: str
    time: float


@dataclass
class PartnershipEvent:
    """Partnership changes (join/split).

    Channel: /events/partnerships/
    """

    joined: list[int]  # [player_pk, partner_pk] when partnering
    split: list[int]  # [player_pk, old_partner_pk] when splitting

    def to_dict(self):
        """Return as dict (without deep copying)"""
        return dict(self.__dict__)


# Helper function for consistent usage
def create_player_hand_event(**kwargs) -> dict:
    """Create a PlayerHandEvent and return as dict with only non-None fields."""
    return PlayerHandEvent(**kwargs).to_dict()


def create_table_event(**kwargs) -> dict:
    """Create a TableEvent and return as dict with only non-None fields."""
    return TableEvent(**kwargs).to_dict()
