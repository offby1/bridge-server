"""LISTEN/NOTIFY-driven SSE broadcaster.

Opens a dedicated psycopg connection, LISTENs on the `bridge_changes` channel,
and turns database change notifications into SSE broadcasts by calling the
matching broadcaster in `app.broadcast`. See docs/README.listen-notify.md.

Singleton by construction: on startup it grabs a Postgres session-level advisory
lock. If another notifier already holds it, this one logs and exits, so
`just runme` (and a redundant Docker service, etc.) can launch one blindly
without risking duplicate broadcasts.
"""

import asyncio
import json
import logging

import psycopg
from asgiref.sync import sync_to_async
from django.core.management.base import BaseCommand
from django.db import close_old_connections, connections

logger = logging.getLogger(__name__)

CHANNEL = "bridge_changes"
# Arbitrary fixed key so every notifier competes for the same advisory lock.
ADVISORY_LOCK_KEY = 8675309
# Back off this long (seconds) before reconnecting after a connection error.
RECONNECT_DELAY = 2.0

# (table, op) -> the app.broadcast function to call for a hand-scoped change.
# These changes carry a hand_id in the payload; _broadcast_hand loads the Hand
# and hands it to the broadcaster. One entry lands per phase, as each inline
# send is removed from the models. Phase 0 ships this empty: the notifier
# observes and logs but broadcasts nothing, so it is safe to run alongside the
# still-inline sends.
HAND_BROADCASTERS: dict[tuple[str, str], str] = {}


def _conninfo() -> str:
    """Build a libpq conninfo string from Django's default DB settings.

    We use a raw psycopg connection (not the Django ORM connection) because this
    is a long-lived, dedicated LISTEN connection.
    """
    db = connections["default"].settings_dict
    return psycopg.conninfo.make_conninfo(
        host=db.get("HOST") or None,
        port=db.get("PORT") or None,
        dbname=db["NAME"],
        user=db.get("USER") or None,
        password=db.get("PASSWORD") or None,
    )


class Command(BaseCommand):
    help = "LISTEN for DB change notifications and drive the matching SSE broadcasts."

    def handle(self, *_args, **_options) -> None:
        try:
            asyncio.run(self._run())
        except KeyboardInterrupt:
            self.stdout.write("notifier: shutting down")

    async def _run(self) -> None:
        conninfo = _conninfo()
        while True:
            try:
                acquired = await self._listen(conninfo)
                if not acquired:
                    return  # another notifier owns the lock; don't spin
            except (psycopg.OperationalError, OSError) as exc:
                logger.warning(
                    "notifier: connection lost (%s); reconnecting in %ss",
                    exc,
                    RECONNECT_DELAY,
                )
                await asyncio.sleep(RECONNECT_DELAY)

    async def _listen(self, conninfo: str) -> bool:
        """Listen until the connection drops. Returns False if another notifier
        already holds the advisory lock (caller should then stop)."""
        aconn = await psycopg.AsyncConnection.connect(conninfo, autocommit=True)
        async with aconn:
            cur = await aconn.execute("SELECT pg_try_advisory_lock(%s)", (ADVISORY_LOCK_KEY,))
            row = await cur.fetchone()
            if not (row and row[0]):
                msg = "notifier: another notifier already holds the advisory lock; exiting"
                self.stdout.write(msg)
                logger.info(msg)
                return False

            await aconn.execute(f"LISTEN {CHANNEL}")
            msg = f"notifier: listening on '{CHANNEL}'"
            self.stdout.write(msg)

            async for notify in aconn.notifies():
                await self._dispatch(notify)
        return True

    async def _dispatch(self, notify: psycopg.Notify) -> None:
        try:
            payload = json.loads(notify.payload)
        except json.JSONDecodeError:
            logger.warning("notifier: unparseable payload %r", notify.payload)
            return

        key = (payload.get("table"), payload.get("op"))

        if key in HAND_BROADCASTERS:
            hand_id = payload.get("hand_id")
            if hand_id is not None:
                await sync_to_async(self._broadcast_hand, thread_sensitive=True)(
                    HAND_BROADCASTERS[key], hand_id
                )
        else:
            logger.debug("notifier: observed (no broadcaster) %s", payload)

    def _broadcast_hand(self, fn_name: str, hand_id: str) -> None:
        import app.broadcast
        from app.models import Hand

        close_old_connections()
        try:
            hand = Hand.objects.get(pk=hand_id)
        except Hand.DoesNotExist:
            logger.info("notifier: hand %s no longer exists; skipping", hand_id)
            return
        getattr(app.broadcast, fn_name)(hand=hand)
