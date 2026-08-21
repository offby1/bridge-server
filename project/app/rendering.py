"""One home for the HTML we build in Python from model objects.

This is presentation, not persistence. These functions used to be methods on the models,
which meant hand.py, player.py and message.py imported ``format_html`` and ``reverse``
for no other reason.

Views and ``app/broadcast.py`` call these functions directly. Templates reach them
through the thin filters in ``app/templatetags/base_extras.py`` and
``app/templatetags/player_extras.py``, which do nothing but delegate here.

The dependency points one way, as it does for ``app/readers.py``: this module imports
from models, and models never import from here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import SafeString

if TYPE_CHECKING:
    from app.models import Hand, Message, Player


def hand_link(hand: Hand | None) -> SafeString:
    """A link to a hand's page, or the empty string when there is no hand."""
    if hand is None:
        return SafeString("")

    return format_html(
        "<a href='{}'>{}</a>",
        reverse("app:hand-dispatch", kwargs={"pk": hand.pk}),
        str(hand),
    )


def player_link(player: Player, style: str = "") -> SafeString:
    """A link to a player's page.  Synthetic players -- bots -- get their name in italics."""
    name: str | SafeString = player.name
    if player.synthetic:
        name = format_html("<i>{}</i>", player.name)

    style_attribute = "" if not style else f'style="{style}"'
    return format_html(
        f'<a {style_attribute} href="{{}}">{{}}</a>',
        reverse("app:player", kwargs={"pk": player.pk}),
        name,
    )


def player_display_name(player: Player) -> SafeString:
    """A player's primary key, then a link to them.  ``four-hands.html`` labels seats with this."""
    return format_html("{}:{}", player.pk, player_link(player))


def message_html(message: Message) -> SafeString:
    """One row of a chat or lobby log.  The views return this, and broadcast.py sends it over SSE."""
    # from_player is nullable -- NULL means "the system" -- but nothing creates such a
    # message today, and this never had a name to print for one.  Say so out loud rather
    # than invent a sender.
    assert message.from_player is not None

    return format_html(
        """
      <div class="chat-message-row">
        <div style="display: inline; font-family: monospace;" class="chat-message-timestamp">{}</div>
        <div style="display: inline;" class="chat-message-sender-name">{}</div>
        <div style="display: inline;" class="chat-message-text">{}</div>
      </div>
        """,
        message.timestamp.isoformat(),
        message.from_player.name,
        message.message,
    )
