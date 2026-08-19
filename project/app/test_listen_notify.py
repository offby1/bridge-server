"""End-to-end test of the LISTEN/NOTIFY plumbing.

pytest's default per-test transaction rolls back, and Postgres only delivers
NOTIFY on COMMIT, so an ordinary test never fires a trigger. This one uses
`transaction=True` so writes actually commit, then checks the chain every
broadcaster rides on: a real DB write -> AFTER trigger -> pg_notify -> a live
LISTEN connection -> the notifier's async `_dispatch`.

Each broadcaster added in later phases is tested directly (by calling the
`app.broadcast` function), because that needs no committed write and no live
listener. This test guards the plumbing underneath them.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import patch

import psycopg
import pytest

import bridge.contract
from app.management.commands.notifier import CHANNEL, Command, _conninfo
from app.models import Hand


@pytest.mark.django_db(transaction=True)
def test_call_write_notifies_and_notifier_broadcasts(usual_setup: Hand) -> None:
    hand = usual_setup

    # A dedicated LISTEN connection, like the real notifier's.
    listen_conn = psycopg.connect(_conninfo(), autocommit=True)
    try:
        listen_conn.execute(f"LISTEN {CHANNEL}")

        # A real, committed write (transaction=True) that inserts an app_call row
        # and so fires the app_call AFTER trigger.
        hand.add_call(call=bridge.contract.Pass)

        # trigger -> NOTIFY: the committed write produced our tiny signal.
        call_notify = None
        for notify in listen_conn.notifies(timeout=5):
            payload = json.loads(notify.payload)
            if payload.get("table") == "app_call":
                call_notify = notify
                break

        assert call_notify is not None, "expected a NOTIFY from the app_call trigger"
        payload = json.loads(call_notify.payload)
        assert payload["op"] == "INSERT"
        assert str(payload["hand_id"]) == str(hand.pk)

        # NOTIFY -> dispatch -> broadcaster -> send_event: the notifier rebuilds
        # and sends the fan-out. It flows through app.models.hand.send_event
        # (directly or via send_timestamped_event), so patch there to observe it.
        with patch("app.models.hand.send_event") as mock_send_event:
            asyncio.run(Command()._dispatch(call_notify))

        assert mock_send_event.called, "the notifier should have broadcast after dispatch"
        sent = [c.kwargs.get("data", {}) for c in mock_send_event.call_args_list]
        assert any(isinstance(d, dict) and "new-call" in d for d in sent), (
            "the rebuilt broadcast should include the new-call event"
        )
    finally:
        listen_conn.close()
