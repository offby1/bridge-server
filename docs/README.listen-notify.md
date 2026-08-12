# Driving SSE off PostgreSQL LISTEN/NOTIFY

## The problem

Every game update reaches the browser (and the bot JSON stream) through a
`send_event(...)` call. Today those calls are scattered across the code: about
ten of them, spread over `models/hand.py`, `models/player.py`,
`models/tournament.py`, `views/lobby.py`, and `views/player.py`. Each is
something a code path has to *remember* to do. Add a new way to change a hand
and forget the broadcast, and the change is invisible until someone reloads.

`docs/README.sse.md` describes the transport (one browser connection, one named
event per kind of update). This document describes a separate concern: **who
fires the broadcast**. The two are complementary.

## The design

A broadcast should follow from the row changing, not from a caller remembering.

1. An `AFTER INSERT OR UPDATE` trigger on the relevant tables emits a *tiny*
   signal on the `bridge_changes` NOTIFY channel: `{table, op, pk, hand_id,
   changed}`. `changed` (UPDATE only) is the list of column *names* whose values
   differ -- never the values, so no card holdings leak and the payload stays
   small. Postgres delivers NOTIFY only on COMMIT, so a rolled-back write never
   broadcasts.
2. A single long-lived `notifier` management command LISTENs on that channel. It
   is a singleton by construction: it takes a session-level advisory lock on
   startup and exits if another notifier already holds it, so anything may launch
   one blindly.
3. For each notification, the notifier calls the matching function in
   `app/broadcast.py`. Those functions run in the notifier's own process, with
   full ORM and template access, so they render the same HTML and send the same
   named events the inline call sites used to -- only now nobody had to remember.

The inline `send_event` calls are removed as each broadcaster takes over its
change, so nothing double-sends.

## Why this branch is a fresh redo

This work was first prototyped on `original-listen-notify-sse`, then adapted onto
the RAPID-refactor branch (now `reference/listen-notify-and-rapid-rewrite`).
Meanwhile `main` reworked the SSE *transport* (named events, one connection).
Rather than merge two SSE reworks, we redo the LISTEN/NOTIFY piece cleanly on top
of main's current design -- broadcasters emit main's named events from the start.
The RAPID refactor is deliberately left on the reference branch; it is a separate
line of work and is **not** part of this branch.

## Testing note

Because Postgres delivers NOTIFY only on COMMIT and pytest's default per-test
transaction rolls back, an ordinary test never fires a trigger. So:

- `test_listen_notify.py` uses `transaction=True` to exercise the real
  trigger -> NOTIFY -> dispatch plumbing once.
- Every broadcaster is otherwise tested **directly**, by calling its
  `app.broadcast` function -- no committed write, no live listener needed.

Tests that used to assert an inline `send_event` fired are updated, as each phase
lands, to call the broadcaster instead.

## Phases

Each phase is one commit; `just ft` stays green after each.

- **Phase 0 (done): plumbing.** Trigger migrations (`0103`, `0104`) for
  Call/Play/Hand/Player, the `notifier` command, the `app/broadcast.py`
  skeleton, and the end-to-end plumbing test. No inline sends removed yet, so
  the notifier observes and broadcasts nothing -- safe to run alongside the
  existing inline sends.
- **Phase 1 (not yet): `Call` INSERT** -> `broadcast_after_call(hand)`; remove
  `add_call`'s inline sends; update affected tests.
- **Phase 2 (not yet): `Play` INSERT** -> `broadcast_after_play(hand)`.
- **Phase 3 (not yet): `Hand` complete/abandoned** -> `broadcast_after_hand_change(hand)`
  (branches on `changed`).
- **Phase 4 (not yet): `Player` bot-toggle** -> `broadcast_player_change(player, changed)`.
- **Phase 5 (not yet): `Message` INSERT** -> `broadcast_after_message(message)`
  (adds an `app_message` trigger); chat and lobby.
- **Phase 6 (not yet): `Player.partner` change** -> partnerships event.

## Status

As of this commit, only Phase 0 has landed: the plumbing exists and is tested,
but no broadcast has moved off its inline call site yet. The remaining phases
are intent, not current behaviour.
