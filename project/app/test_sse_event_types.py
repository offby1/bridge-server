"""Check that the browser subscribes to the event names the server sends.

Event names are a contract between Python and JavaScript that no type checker sees.
Rename one end and the other goes quiet: no error, no failing request, just updates
that stop arriving. That is a miserable thing to debug, and it is exactly the risk we
took on by replacing the single `"message"` event with one name per kind of update.

These tests are deliberately crude -- they look for the literal name in the file that
subscribes to it. A crude check that fires is worth more than an elegant one we don't
write.
"""

from pathlib import Path

import pytest

from app.sse_events import SSEEventTypes

APP_DIR = Path(__file__).resolve().parent

# Each browser-side event name, and the file that must subscribe to it.
SUBSCRIBERS = [
    (SSEEventTypes.PLAYER_HAND, "static/app/bridge-game.js"),
    (SSEEventTypes.TABLE, "static/app/bridge-game.js"),
    (SSEEventTypes.TABLE, "templates/read-only_hand.html"),
    (SSEEventTypes.BOT_CHECKBOX, "templates/base.html"),
    (SSEEventTypes.CHAT, "templates/chat-partial.html"),
]


@pytest.mark.parametrize(("event_type", "relative_path"), SUBSCRIBERS)
def test_browser_subscribes_to_the_event_name_we_send(event_type: str, relative_path: str) -> None:
    source = (APP_DIR / relative_path).read_text()
    assert event_type in source, (
        f"{relative_path} does not mention the {event_type!r} event. "
        f"If you renamed it in SSEEventTypes, rename it here too, or the browser "
        f"will silently stop receiving these updates."
    )


def test_no_browser_event_is_still_called_message() -> None:
    """`"message"` is SSE's default name, so it is the easy thing to leave behind.

    The JSON stream at /events/player/json/ is exempt by design -- but it too now uses
    per-kind names, so nothing should be called "message" any more.
    """
    names = {
        value
        for name, value in vars(SSEEventTypes).items()
        if not name.startswith("_") and isinstance(value, str)
    }
    assert "message" not in names
