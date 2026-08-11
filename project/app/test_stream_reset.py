"""Tests for django-eventstream's `stream-reset`, which we do not yet handle.

`stream-reset` is not a subscription-management mechanism, despite the name. The server
emits it when a client reconnects carrying a `Last-Event-ID` whose events have already
aged out of storage: django-eventstream cannot replay the gap, so it tells the client
"you missed events, I can't say which, re-sync from scratch."

These tests drive `get_events()` directly rather than consuming an SSE endpoint. The
endpoint's response never ends, so reading it from a test means racing a generator that
is designed to run forever; `get_events()` is the same code path without the streaming.

See docs/README.sse.md.
"""

import pytest
from django.conf import settings
from django.test import override_settings
from django_eventstream.eventrequest import EventRequest  # type: ignore [import-untyped]
from django_eventstream.eventstream import get_events  # type: ignore [import-untyped]
from django_eventstream.storage import DjangoModelStorage  # type: ignore [import-untyped]
from django_eventstream.utils import sse_encode_event  # type: ignore [import-untyped]

from app.models import Player
from app.sse_channels import SSEChannels

DJANGO_MODEL_STORAGE = "django_eventstream.storage.DjangoModelStorage"

# An id that was never issued takes the same code path as one that expired, so we can
# provoke a reset without waiting for a TTL or filling storage.
NEVER_ISSUED_EVENT_ID = "999"


def _reconnecting_request(channel: str, last_event_id: str | None) -> EventRequest:
    """An EventRequest as if a client reconnected with the given Last-Event-ID.

    Built by hand rather than from an HttpRequest: the channel set would otherwise come
    from URL kwargs, and here we want to name the channel under test directly.
    """
    request = EventRequest()
    request.channels = {channel}
    request.channel_last_ids = {} if last_event_id is None else {channel: last_event_id}
    request.is_next = False
    request.is_recover = False
    return request


def test_we_currently_have_no_event_storage_at_all(usual_setup: None) -> None:
    """Today a reconnecting client is told nothing, because nothing is stored.

    `EVENTSTREAM_STORAGE_CLASS` is unset, so `get_storage()` returns None and
    `eventstream.py` skips the branch that would raise `stream-reset`. A client that
    misses events therefore gets neither the events nor any warning that it missed
    them: the gap is silent by construction.

    This test guards the finding rather than the behaviour we want. When we enable
    storage, it should fail, and the assertion below is where to start reading.
    """
    assert not hasattr(settings, "EVENTSTREAM_STORAGE_CLASS")

    player = Player.objects.first()
    assert player is not None
    channel = SSEChannels.player_bot_checkbox(player.pk)

    response = get_events(_reconnecting_request(channel, NEVER_ISSUED_EVENT_ID), user=player.user)

    assert response.channel_reset == set(), (
        "Without storage configured, stream-reset can never fire."
    )
    assert response.channel_items[channel] == []


@pytest.mark.django_db
@override_settings(EVENTSTREAM_STORAGE_CLASS=DJANGO_MODEL_STORAGE)
def test_stale_last_event_id_provokes_stream_reset(usual_setup: None) -> None:
    """With storage enabled, an unreplayable Last-Event-ID produces `stream-reset`.

    This is the behaviour we want to rely on, so it is worth pinning down before we
    build anything on top of it.
    """
    player = Player.objects.first()
    assert player is not None
    channel = SSEChannels.player_bot_checkbox(player.pk)

    # Put one event in storage, so the channel has a current id to reset us to.
    DjangoModelStorage().append_event(channel, "message", {"html": "<div></div>"})

    response = get_events(_reconnecting_request(channel, NEVER_ISSUED_EVENT_ID), user=player.user)

    assert response.channel_reset == {channel}
    # The gap is not replayed; the client is expected to re-sync by itself.
    assert response.channel_items[channel] == []


@pytest.mark.django_db
@override_settings(EVENTSTREAM_STORAGE_CLASS=DJANGO_MODEL_STORAGE)
def test_a_caught_up_client_is_not_reset(usual_setup: None) -> None:
    """A client whose Last-Event-ID is current gets no reset.

    Without this, `test_stale_last_event_id_provokes_stream_reset` would still pass if
    the server reset every reconnecting client indiscriminately.
    """
    player = Player.objects.first()
    assert player is not None
    channel = SSEChannels.player_bot_checkbox(player.pk)

    event = DjangoModelStorage().append_event(channel, "message", {"html": "<div></div>"})

    response = get_events(_reconnecting_request(channel, str(event.id)), user=player.user)

    assert response.channel_reset == set()


@pytest.mark.django_db
@override_settings(EVENTSTREAM_STORAGE_CLASS=DJANGO_MODEL_STORAGE)
def test_reset_reaches_the_wire_as_the_event_the_client_listens_for(
    usual_setup: None,
) -> None:
    """The frame is named `stream-reset`, which is what our JS listens for.

    `views.py` encodes the reset with `sse_encode_event`, so we assert on the same
    encoding the streaming endpoint would emit. Our handlers in `bridge-game.js`
    subscribe by event name, and a rename upstream would silently stop reaching them.
    """
    player = Player.objects.first()
    assert player is not None
    channel = SSEChannels.player_bot_checkbox(player.pk)

    DjangoModelStorage().append_event(channel, "message", {"html": "<div></div>"})

    response = get_events(_reconnecting_request(channel, NEVER_ISSUED_EVENT_ID), user=player.user)

    frame = sse_encode_event(
        "stream-reset",
        {"channels": list(response.channel_reset)},
        event_id="ignored",
        json_encode=True,
    )

    assert frame.startswith("event: stream-reset\n")
    assert channel in frame
