# Front-End Refactoring Summary (historical)

**Read this as history, not as a description of the code today.** In late 2025 we did
three front-end refactorings, summarised below. Each of the three has since been extended
or partly superseded, and the current design is documented elsewhere:

- [`docs/README.sse.md`](docs/README.sse.md) — the browser's SSE connection as it stands
  today, and why there is exactly one of it per page
- [`docs/README.listen-notify.md`](docs/README.listen-notify.md) — who fires a broadcast
  now (a Postgres trigger and the `notifier`, not the write path)

Where this document and those two disagree, they are right.

## What the three refactorings did

### 1. Extracted inline JavaScript to an external module

`project/app/static/app/bridge-game.js` replaced about 115 lines of SSE event handling
embedded in `interactive_hand.html` with a module the template imports in a dozen lines.
The functions got names, JSDoc, and single responsibilities.

The file has roughly doubled since — it has grown reconnect handling, `pagehide`
teardown, and the `stream-reset` handlers — and it no longer opens its own `EventSource`.
`base.html` opens the one connection and parks it in `window.bridgeEventSource`;
`bridge-game.js` listens on that.

### 2. SSE event contracts (dataclasses)

`project/app/sse_events.py` defines the shape of each event as a dataclass, with
`create_player_hand_event()` / `create_table_event()` helpers that drop `None` fields so
payloads stay small. IDE autocomplete and type hints replaced a bare dict whose keys you
had to guess.

Since then the module also grew `SSEEventTypes`, the registry of `event:` names, which
matters more than the payload shapes: the browser subscribes *by name*, so a rename that
touches only one side goes quiet with no error. `app/test_sse_event_types.py` pins the two
halves together.

### 3. SSE channel-name registry

`project/app/sse_channels.py` centralised channel-name generation:
`SSEChannels.LOBBY`, `.PARTNERSHIPS`, `.ALL_TABLES`, and the parameterised
`player_html_hand()`, `player_json()`, `player_bot_checkbox()` and `table_html()`.

One correction worth recording, because this document originally listed it as a feature:
the class briefly had a `chat_player_to_player()` that prefixed `chat:player-to-player:`.
That was the URL path of the old per-channel endpoint, not a channel name, and nothing
ever published to it. A chat channel is `players:<pk>_<pk>`, built by
`Message.channel_name_from_player_pks`, and that is the only place that should know the
format.

## What has changed since

- **`"message"` is gone as an event name.** These refactorings still sent everything as
  `"message"`, which worked only because each channel had a connection of its own. The
  channels now share one connection, so every kind of update needs a name of its own.
- **The `send_event` call sites have moved.** This document's "future work" suggested
  migrating the remaining ones to use the event contracts. What happened instead is
  bigger: nine of the ten scattered call sites became broadcasters in
  `project/app/broadcast.py`, called by the `notifier` when a Postgres trigger fires. The
  code samples below, which show a model calling `send_event` directly, are no longer how
  a broadcast is written.
- **Read-only query logic left the models** into `project/app/readers.py`; see
  [`docs/README.rapid-readers.md`](docs/README.rapid-readers.md).

## Migration notes (as written at the time)

**No breaking changes**: the refactoring only added abstraction layers.

**Performance impact**: none. The JavaScript module uses ES6 imports, the event contracts
compile to identical dicts at runtime, and the channel registry functions are string
formatters.
