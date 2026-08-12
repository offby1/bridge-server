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

import psycopg
import pytest

import bridge.contract
from app.management.commands.notifier import CHANNEL, Command, _conninfo


@pytest.mark.django_db(transaction=True)
def test_committed_call_fires_notify(usual_setup) -> None:
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

        # Phase 0's dispatch only observes; it must handle the notify without raising.
        asyncio.run(Command()._dispatch(call_notify))
    finally:
        listen_conn.close()
