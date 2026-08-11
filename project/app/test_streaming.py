"""Do events actually reach a client over the wire?  SKIPPED; see below.

Every other test stops short of that. `test_reference_client.py` covers the HTTP half
against `live_server`, and `test_sse_event_types.py` checks that the names the server
sends are the names the browser subscribes to -- but nothing here has read an event off
a live connection.

`live_server` can't do it. Django's `LiveServerThread` hardcodes `ThreadedWSGIServer`
(`django/test/testcases.py:1735-1761`), django-eventstream yields async iterables, and
so under `live_server` they arrive through an `async_to_sync` fallback rather than the
path we ship. A test could pass here while production was broken. So we run daphne,
which is what production runs.

That costs us the shared transaction: a separate process cannot see uncommitted data,
hence `django_db(transaction=True)` throughout, which is slower and truncates tables
between tests.

## Why these are skipped

They have never passed. The fixture below is sound -- daphne starts, serves, and
authenticates, and the stream opens; you can watch it do so in the captured output. What
doesn't happen is delivery: an event published by the test process never reaches a
client connected to that freshly-started server.

Ruled out, each verified directly: Redis pub/sub between processes, both with a sync
subscriber and an async one; the database the subprocess talks to; authentication; and
the channel name, which the server logs as exactly the one we publish to.

The remaining suspicion is upstream. `ListenerManager.add_listener` sets
`redis_listener_started` on the first listener and never clears it, and it starts the
subscriber with `loop.create_task(...)` without keeping the result -- a task with no
strong reference can be collected mid-flight. If that first task doesn't survive, no
later connection revives it. That fits the evidence: this works in the Docker stack,
where the process is warm and connections are long-lived, and fails in a fresh server
whose first connection is short.

Whether it is worth chasing is a separate question from whether it is true. Events
crossing processes is already demonstrated daily by the bot and the browser, so what
these tests would add is regression protection, not knowledge. Left here rather than
deleted because the daphne fixture is the reusable part, and because a file explains
itself better than a deletion does.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
import requests
from django.db import connection
from django_eventstream import send_event  # type: ignore [import-untyped]

from app.models import Hand, Player
from app.reference_client import BridgeClient
from app.sse_channels import SSEChannels
from bridge.contract import Bid as libBid

pytestmark = pytest.mark.skip(
    reason="Events never arrive from a freshly-started daphne; see this module's docstring"
)

PASSWORD = "sekrit"
PROJECT_DIR = Path(__file__).resolve().parent.parent
STARTUP_TIMEOUT_SECONDS = 30
SHUTDOWN_TIMEOUT_SECONDS = 5

# Long enough that a working server always beats it, short enough that a broken one
# fails the test rather than hanging the suite. Keep it under django-eventstream's
# 20-second keep-alive, or a quiet connection looks identical to a dead one.
READ_TIMEOUT_SECONDS = 10

# Used to find out when the server has started forwarding events; see
# _wait_until_the_server_forwards_events.
PROBE_EVENT = "test-probe"
PROBE_INTERVAL_SECONDS = 0.5
PROBE_GIVE_UP_SECONDS = 20


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture
def daphne_server() -> Iterator[str]:
    """A real ASGI server, pointed at the test database, on a port of its own."""
    port = _free_port()
    env = os.environ | {
        "DJANGO_SETTINGS_MODULE": "project.test_settings",
        # The whole reason test_settings reads this from the environment. Django
        # rewrote the name when it created the test database; ask it what it chose
        # rather than assuming "test_bridge".
        "PGDATABASE": connection.settings_dict["NAME"],
        "PYTHONUNBUFFERED": "t",
    }

    server = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "daphne",
            "--bind",
            "127.0.0.1",
            "--port",
            str(port),
            "--verbosity",
            "0",
            "project.asgi:application",
        ],
        cwd=PROJECT_DIR,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
    while True:
        if server.poll() is not None:
            raise RuntimeError(f"daphne died during startup:\n{server.communicate()[0]}")
        try:
            requests.get(url, timeout=1)
            break
        except requests.exceptions.RequestException:
            if time.monotonic() > deadline:
                server.kill()
                raise RuntimeError(f"daphne never answered on {url}")
            time.sleep(0.1)

    try:
        yield url
    finally:
        server.terminate()
        try:
            output = server.communicate(timeout=SHUTDOWN_TIMEOUT_SECONDS)[0]
        except subprocess.TimeoutExpired:
            server.kill()
            output = server.communicate()[0]
        # pytest swallows this unless the test failed, which is exactly when a silent
        # server is the most maddening thing in the world.
        print(f"--- daphne said ---\n{output}\n--- end ---")


@pytest.fixture
def client_at(daphne_server: str, usual_setup: Hand) -> tuple[BridgeClient, Hand]:
    """A client logged in as somebody sitting at the fixture's hand."""
    hand = usual_setup
    player = hand.player_who_may_call
    assert player is not None

    user = player.user
    user.set_password(PASSWORD)
    user.save()

    client = BridgeClient(daphne_server)
    client.log_in(user.username, PASSWORD)
    return client, hand


# The events that mean something happened, as opposed to the stream's own
# housekeeping.  Selected by name rather than by filtering housekeeping out, because
# sseclient reports the stream's opening padding as a default "message" frame -- a
# blocklist would let that through and we would mistake it for news.
MEANINGFUL_EVENTS = {"new-call", "new-play", "contract", "bot-setting"}


def _next_interesting_event(events: Iterator[tuple[str, str]]) -> tuple[str, dict]:
    """Return the first event that says something happened."""
    for event_type, data in events:
        if event_type not in MEANINGFUL_EVENTS:
            continue
        return event_type, json.loads(data)
    raise AssertionError("The stream ended without saying anything")


def _stream_that_is_definitely_forwarding(
    client: BridgeClient, channel: str
) -> Iterator[tuple[str, str]]:
    """Open a stream and return it only once an event has demonstrably crossed it.

    Two things make this necessary, and neither shows up as an error anywhere.

    With EVENTSTREAM_REDIS set, `send_event` publishes to Redis and skips local
    listeners entirely, and the server only SUBSCRIBEs in a background task kicked off
    by the first listener (django_eventstream/views.py:81-88). Redis pub/sub keeps
    nothing for a subscriber that hasn't arrived yet, so anything published in the
    meantime is simply gone.

    Worse, that task is created once and never again: `redis_listener_started` is set on
    the first listener and never cleared. So we hold this connection open rather than
    reconnecting between attempts -- if the first listener's task doesn't survive, no
    later connection will revive it, and reconnecting would poll a server that can never
    answer.

    Probes are published from a background thread because reading blocks.
    """
    events = client.events(read_timeout=READ_TIMEOUT_SECONDS)
    next(events)  # a frame means the HTTP connection is up

    stop = threading.Event()

    def probe_until_told_to_stop() -> None:
        while not stop.wait(PROBE_INTERVAL_SECONDS):
            send_event(channel=channel, event_type=PROBE_EVENT, data={})

    prober = threading.Thread(target=probe_until_told_to_stop, daemon=True)
    prober.start()
    try:
        deadline = time.monotonic() + PROBE_GIVE_UP_SECONDS
        for event_type, _ in events:
            if event_type == PROBE_EVENT:
                return events
            if time.monotonic() > deadline:
                break
    finally:
        stop.set()
        prober.join(timeout=PROBE_INTERVAL_SECONDS * 2)

    raise AssertionError(
        f"No probe came back on {channel} in {PROBE_GIVE_UP_SECONDS}s; "
        "the server never started forwarding events from Redis"
    )


@pytest.mark.django_db(transaction=True)
def test_a_call_reaches_a_listening_client(client_at: tuple[BridgeClient, Hand]) -> None:
    """The claim the whole SSE apparatus exists to make."""
    client, hand = client_at
    assert client.player_pk is not None
    events = _stream_that_is_definitely_forwarding(
        client, SSEChannels.player_json(client.player_pk)
    )

    hand.add_call(call=libBid.deserialize("Pass"))

    event_type, data = _next_interesting_event(events)

    assert event_type == "new-call"
    assert data["new-call"]["serialized"] == "Pass"


@pytest.mark.django_db(transaction=True)
def test_nothing_arrives_for_a_hand_we_are_not_at(daphne_server: str, usual_setup: Hand) -> None:
    """A player's stream carries their events, not everybody's.

    Without this, the test above would pass just as happily if the server broadcast
    every event to every listener.
    """
    hand = usual_setup
    caller = hand.player_who_may_call
    assert caller is not None
    eavesdropper = Player.objects.exclude(pk__in=[p.pk for p in hand.players()]).first()
    if eavesdropper is None:
        pytest.skip("This fixture seats everybody, so nobody is left to eavesdrop")

    user = eavesdropper.user
    user.set_password(PASSWORD)
    user.save()
    client = BridgeClient(daphne_server)
    client.log_in(user.username, PASSWORD)

    events = client.events(read_timeout=READ_TIMEOUT_SECONDS)
    next(events)

    hand.add_call(call=libBid.deserialize("Pass"))

    with pytest.raises(requests.exceptions.RequestException):
        _next_interesting_event(events)
