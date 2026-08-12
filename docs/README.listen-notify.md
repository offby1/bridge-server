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
- **Phase 1 (done): `Call` INSERT** -> `broadcast_after_call(hand)`. `add_call`'s
  inline SSE fan-out is gone; only the passed-out state change stays. `testutils`
  helpers call the broadcaster after each `add_call` to emulate the notifier, so
  tests that observe those events still see them.
- **Phase 2 (done): `Play` INSERT** -> `broadcast_after_play(hand)`.
  `add_play_from_model_player`'s inline sends (the JSON new-play, the trick
  table, and the per-seat hand updates) are gone; only the hand-completion state
  change stays. The just-played seat comes from `hand.annotated_plays[-1]`.
- **Phase 3 (done): `Hand` complete/abandoned** -> `broadcast_after_hand_change(hand, changed)`.
  Branches on `changed`: `is_complete` sends the final score (reconstructing the
  text from hand state), `abandoned_because` sends the play-completion deadline
  (only when the tournament is complete, so ordinary splitsville abandonment
  stays silent as before). `do_end_of_hand_stuff` and `Tournament._finish_play`
  no longer send. The notifier now forwards `changed` to hand broadcasters.
- **Phase 4 (done): `Player` bot-toggle** -> `broadcast_player_change(player, changed)`.
  The player's own bot-checkbox HTML, the JSON bot-setting, and (for a declarer)
  the dummy's checkbox. `Player._broadcast_changes` is gone; `Player.save` no
  longer broadcasts. Driven by the app_player UPDATE trigger (0104), which
  already fires only on allow_bot / current_hand changes.
- **Phase 5 (done): `Message` INSERT** -> `broadcast_after_message(message)`
  (adds the `app_message` trigger, migration 0105). Covers private chat (CHAT)
  and lobby announcements (LOBBY), including the partnership-JOIN lobby message;
  the recipient tells the broadcaster which. `Message.create_*_event_args` became
  `create_*_message` (create the row, don't build/send the event); the two chat
  views and `_send_partnership_messages` just create the row now.
- **Phase 6 (deliberately left inline): the `PARTNERSHIPS` event.** This is the
  one broadcast we do *not* drive from a trigger, because it doesn't fit the
  re-derive-from-committed-state model:
  - A SPLIT event needs the *old* partner's pk. After `break_partnership`
    commits, `self.partner` is `None`, and the payload carries only changed
    column *names*, never values -- so the old pk isn't recoverable.
  - A partnership change updates *both* players' `partner_id`, so a
    `partner_id`-driven trigger would fire the single event twice, needing dedup.
  - Nothing subscribes to `PARTNERSHIPS` today, so forcing it into the trigger
    model would add complexity (old values in the payload + dedup) for no payoff.

  It stays inline in `Player._send_partnership_messages`, with a comment there. If
  a subscriber is ever added and this needs to be trigger-driven, the trigger
  function would have to start carrying selected old column values.

## Status

This work is complete. Nine of the ten original scattered `send_event` sites are
now trigger-driven, in `app/broadcast.py`, called by the `notifier`. The tenth,
the `PARTNERSHIPS` event, deliberately stays inline (Phase 6 above). The only
other `send_event` in the models is inside `send_timestamped_event`, the shared
helper the broadcasters use -- not a "remember to broadcast" call site.
