"""SSE broadcasters driven by the `notifier` command.

Every function here reproduces one model change's SSE fan-out: given the row that
changed (a Hand, a Player, a Message), it renders and sends exactly the events
the models used to send inline from `send_event`/`send_timestamped_event` call
sites. The `notifier` management command calls these in its own process, on
COMMIT, in response to a PostgreSQL NOTIFY (see docs/README.listen-notify.md).

The point of moving the sends here: a broadcast is no longer something a code
path has to remember to do. It follows from the row changing, so it cannot be
forgotten.

This module is filled in one broadcaster per phase; today (Phase 0) it is a
skeleton and nothing calls it yet.
"""
