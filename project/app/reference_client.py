"""A worked example of a client for this server's API.

This exists to be read. If you want to write a bot, or your own user interface, copy
this file and start editing: it depends only on `requests` and `sseclient`, and it uses
nothing from Django or from the rest of this project.

It is also what our contract tests drive, which is deliberate. An example nobody runs
rots quietly; this one fails the build instead. See `app/test_reference_client.py` and
`docs/README.api.md`.

The shape of the thing:

    client = BridgeClient("http://localhost:9000")
    me = client.log_in("bob", "sekrit")
    hand = client.hand(me["hand_pk"])
    client.call("1♣")
    for event_type, data in client.events(me["player_pk"]):
        ...

Two notes that will save you an afternoon:

- `call()` and `play()` don't take a hand: the server applies them to whichever hand
  you're currently seated at.
- Events carry no history. If you disconnect, whatever happened while you were away is
  gone, and no amount of reconnecting will replay it. Fetch `hand()` again instead --
  that is the intended recovery, not an admission of defeat.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Any

import requests
import sseclient  # type: ignore [import-untyped]

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 10


class BridgeClientError(Exception):
    """The server refused something. `response` holds its side of the story."""

    def __init__(self, message: str, response: requests.Response) -> None:
        super().__init__(f"{message}: {response.status_code} {response.text[:200]}")
        self.response = response


class BridgeClient:
    """One authenticated player's view of the server."""

    def __init__(self, base_url: str, *, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.player_pk: int | None = None

    def _url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"

    def log_in(self, username: str, password: str) -> dict[str, Any]:
        """Exchange a username and password for the session cookies we'll reuse.

        The reply names your player, and -- if you're seated -- the hand you're at.
        """
        response = self.session.get(
            self._url("/three-way-login/"),
            auth=(username, password),
            timeout=self.timeout,
        )
        if not response.ok:
            raise BridgeClientError("Could not log in", response)

        body = response.json()
        self.player_pk = body["player_pk"]
        return body

    def hand(self, hand_pk: int) -> dict[str, Any]:
        """Everything you're allowed to know about a hand, as of right now.

        Your own cards, the calls and plays so far, and the dummy's cards once they're
        exposed. Call this whenever you're unsure you're up to date; it is cheap and it
        is the truth.
        """
        response = self.session.get(
            self._url(f"/serialized/hand/{hand_pk}/"),
            headers={"Accept": "application/json"},
            timeout=self.timeout,
        )
        if not response.ok:
            raise BridgeClientError(f"Could not read hand {hand_pk}", response)
        return response.json()

    def call(self, call: str, *, explanation: str = "") -> None:
        """Bid, pass, double or redouble -- e.g. "1♣", "Pass", "Double".

        Applies to the hand you're seated at; there is nowhere to say which.
        """
        payload = {"call": call}
        if explanation:
            payload["explanation"] = explanation
        self._post("/call/", payload)

    def play(self, card: str) -> None:
        """Play a card, e.g. "♠A". Applies to the hand you're seated at."""
        self._post("/play/", {"card": card})

    def _post(self, path: str, payload: dict[str, str]) -> None:
        # Django wants the CSRF token echoed back in a header. The cookie arrives with
        # the login response, and `self.session` has been holding onto it since.
        headers = {"X-CSRFToken": self.session.cookies.get("csrftoken", "")}
        response = self.session.post(
            self._url(path), data=payload, headers=headers, timeout=self.timeout
        )
        if not response.ok:
            raise BridgeClientError(f"Server refused {payload}", response)

    def events(
        self, player_pk: int | None = None, *, read_timeout: float | None = None
    ) -> Iterator[tuple[str, str]]:
        """Yield `(event_type, raw_json)` as the server sends them.

        Event types are the ones in `app/sse_events.py`: "new-call", "new-play",
        "contract", "bot-setting". You'll also see "stream-open" and "keep-alive",
        which carry nothing and which you can ignore.

        Without `read_timeout` this blocks forever, which is usually what a bot wants:
        break out of the loop when you've had enough. Pass one if you'd rather give up
        after a quiet spell -- a test waiting for a particular event wants that, so it
        fails instead of hanging. Note the server sends a keep-alive every 20 seconds,
        so a timeout longer than that will never fire on a healthy connection.

        Remember the warning about history in this module's docstring: whatever you
        missed while disconnected is gone, so re-read `hand()` after any interruption.
        """
        if player_pk is None:
            player_pk = self.player_pk
        if player_pk is None:
            raise ValueError("Log in first, or say whose events you want")

        messages = sseclient.SSEClient(
            self._url(f"/events/player/json/{player_pk}/"),
            session=self.session,
            timeout=read_timeout,
        )
        for message in messages:
            yield message.event, message.data
