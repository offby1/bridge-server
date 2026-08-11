# Branch goal: one SSE connection per browser, not six

**Status: the consolidation has landed and works.** A page holds one connection, plus
`django_browser_reload`'s in development. We watched the open count stay at two while
clicking around, where it used to reach six and wedge the browser.

Landed:

- `app/middleware/sse_stream_log.py` logs every stream's open and close, with a reason,
  a duration and a running count. This is how we measured all of the above.
- Every kind of update has its own event name (`app/sse_events.py`, `SSEEventTypes`),
  on the JSON stream as well as the browser's.
- `/events/all/` carries every browser channel, with `MyChannelManager` deciding which
  ones for the requesting viewer.
- The client closes its connection on `pagehide`, so a socket comes back immediately
  rather than 55 to 70 seconds later.
- `can_read_channel` denies channel names it doesn't recognise.
- `app/test_stream_reset.py` records that `stream-reset` cannot fire here.
- The superseded per-channel endpoints are gone. `/events/all/` and
  `/events/player/json/<player_id>/` are the only two left.

Verified in a browser: a page holds one connection, chat delivers over it, and a hand
page's auction and play histories update as the bot plays. That last one was the
complaint this work started from.

- A reconnect reloads the page, so a client that was away catches up.

Still intent: the reference client with its contract tests.

Throughout this document, "today" and "currently" describe the repository as it stands;
"we will" and "this branch will" describe work not yet done. Where a sentence could be
read either way, it's a bug in the document.

**Also on this branch, and unrelated to SSE:** `app/management/commands/tournament_clock.py`
replaced a `request_finished` signal that honoured tournament deadlines. It's here
because we did it here, and it could be cherry-picked out on its own; see
`advance_expired_tournaments` for why the signal had to go.

## What this branch does

This branch collapses the browser's per-channel `/events/...` endpoints into one, whose
channel set the server computes per request. It leaves the programmatic JSON endpoint as
it is, and it will give both kinds of client a recovery story for events they miss —
that last part is the piece still outstanding.

## Why

Browsers allow only six concurrent HTTP/1.1 connections per origin, shared across tabs.
Today each SSE channel has its own endpoint and therefore its own socket, and a
departed page's stream lingers for up to 70 seconds, because django-eventstream only
notices the client left when a keep-alive write fails. A few ordinary navigations
exhaust the budget, after which the browser silently queues every further request
instead of sending it. We measured one POST that spent 42 seconds waiting in Chrome's
queue and 82ms at the server.

Production terminates TLS at Caddy and so gets HTTP/2, which multiplexes and mostly
hides this. Development serves plain HTTP/1.1 and does not. One connection would keep
us clear either way, and it is tidier regardless of transport.

## How it works

**One browser endpoint.** `/events/all/` hardcodes no channels;
`MyChannelManager.get_channels_for_request()` returns the viewing player's own channels
(bot-checkbox, private hand HTML) plus the table and chat channels the page asks for
through `?hand=` and `?chat=`. `<body>` in `base.html` owns the connection, and htmx's
SSE extension attaches every descendant `sse-swap` element to it, so the navbar
checkbox, the chat log and the hand all share one socket. `base.html` opens it before
htmx can, keeping the reference in `window.bridgeEventSource` so `bridge-game.js` can
listen on the same object rather than constructing more.

This needed no new machinery. `django_eventstream` already asks the channel manager for
a channel set when a URL doesn't hardcode one (`eventrequest.py:60-66`), and
`app/channelmanager.py` already existed.

The manager filters its own result through `can_read_channel` rather than leaving that
to `get_events()`, which refuses the *entire* request if any single channel is
unreadable — on a shared connection that would cost a viewer every update rather than
the one they may not have.

**We did not touch `/events/player/json/<player_id>/`.** It is the interface a third
party would write a client against, it carries JSON rather than HTML fragments, and a
programmatic client does not compete for a browser's six sockets. Consolidating it would
serve nobody.

**`lobby`, `all-tables` and `partnerships` are deliberately absent** from the
consolidated set: nothing in the browser subscribes to them. They remain readable, so
adding a subscriber later is a one-line change.

### Why one browser endpoint rather than two

Splitting into a public stream and a private one sounds tidy, but it would reduce
nothing today: `can_read_channel` returns `False` for anyone without a player
(`channelmanager.py:16-25`), so anonymous visitors currently read nothing at all. Every
client that reads anything is authenticated and would therefore hold both connections,
which is two sockets per tab where one would do.

We do want unauthenticated users to observe games in progress some day. When that
happens, some channels will become readable without a player, and a second public
endpoint will start earning its socket. That is a change to `can_read_channel` first;
the split follows from it rather than preceding it.

### What the three anticipated problems turned out to be

- **Event types.** Every `send_event` used to pass `"message"`, which worked only
  because each channel had its own connection. Each kind of update now has its own
  name, collected in `SSEEventTypes`. We predicted this would be the bulk of the work
  and were wrong: about ten call sites, most already funnelling through
  `send_timestamped_event`, and five client subscription points. The care was all on
  the client side, and `app/test_sse_event_types.py` guards that the two agree, since
  no type checker sees across that boundary.
- **The table channel is page-dependent**, as expected, so pages pass it in. What we
  didn't anticipate: a query parameter that doesn't parse becomes a channel name, and
  `can_read_channel` used to allow anything it didn't recognise. That produced two bugs
  in a day — `?hand=abc`, and a chat name carrying a URL prefix that no publisher uses
  — and is why that function now denies by default.
- **The channel set is bound at connect time**, still true. Nothing can add a channel to
  a live connection; a client must close and reopen its `EventSource`. A page navigation
  does that for free, and now closes the old one on the way out.

## Recovery: re-sync from truth, not replay

**The contract we intend:** when a client misses events, it re-reads current state
rather than asking for the events it missed.

Part of that already exists. `bridge-game.js:76-80` reloads the page outright on a phase
transition instead of patching the DOM, and `/serialized/hand/<pk>/` (`app/urls.py:45`)
already serves full state to API clients. What does not exist today is anything that
notices a client *should* re-sync; that part is this branch's work.

**We will leave event persistence off.** It is already off today, so this is a decision
to keep the status quo rather than to change it — but the status quo arrived by accident,
and the history reads the other way at a glance:

- **2025-06-04, `0bd4455f`** (perf branch) disabled persistence as a performance
  experiment, in the middle of a run of OOM and ulimit firefighting.
- **2025-06-06, `94bce2af`** restored it, because "we won't find half of our tables just
  sitting there, because one of the bots missed an event."
- **2025-06-30, `86677f9b`** replaced `EVENTSTREAM_STORAGE_CLASS` with
  `EVENTSTREAM_REDIS` while pulling Redis in. Those settings control different
  subsystems: the first is persistence, the second is the pub/sub transport. Persistence
  has been off ever since, apparently unintentionally.

The 2025-06-06 reason no longer applies. Nothing that advances a game reads SSE any
more: `docker-compose.yaml:76` runs `cheating_bot`, a single process that polls the
database on behalf of every bot player and contains no SSE code at all. A browser that
misses events shows a stale page, which a reload fixes; it does not stall a hand.

Because persistence stays off, `stream-reset` will continue never to fire.
`app/test_stream_reset.py` already records both halves of that: one test pins the
storage-free behaviour and will fail the day anyone enables storage, and the others show
what the mechanism would do if we did.

**The catch, and where it now stands.** A reconnect carries no notification that
anything was missed, so reacting to reconnects is all we have. That used to be
unaffordable: streams re-dialled about once a minute, and reloading the page that often
during an auction would be worse than the staleness.

Consolidation changed the arithmetic. A page holds one connection instead of four, and
closing it on `pagehide` means the re-dials we were counting were mostly abandoned pages
being reaped, not live ones flapping. A live tab now holds its connection for as long as
it's open — we watched one last five minutes.

So `base.html` now reloads the page when the connection reopens, having been open
before. We considered re-fetching the hand fragment over htmx instead, to keep scroll
position and focus, but a reload is what this codebase already does when an incremental
update won't serve, and it needs no per-page knowledge of which fragments to re-read.
If interrupting a bidding box turns out to annoy, the fragment approach is the upgrade.

Two guards come with it. The first `open` is the initial connection, not a reconnect, so
it does nothing. And a page younger than ten seconds doesn't reload, which both avoids
pointless work and bounds us to one reload per ten seconds if the server is flapping,
because each reload restarts that clock.

`stream-reset` remains log-only in `bridge-game.js`, and the handlers now say why: it
cannot fire without event storage, and reconnect handling is the real recovery.

## A reference client that is also the contract tests

Keeping the JSON endpoint means owing its consumers a working interface. Today nothing
outside `test_hand_events.py:44` and `test_hand.py:305` touches `player:json:*`, and
those assert that events are *sent*, not that a client can follow a hand from them. The
old per-player API bot used to keep the endpoint honest, and it is gone.

So we will write one client and use it twice: as the example a third party reads, and as
the thing our tests drive.

**The client we will write.** A small module depending only on `requests` and
`sseclient`, both already declared in `pyproject.toml` and both currently unused, so it
will add no dependencies and a third party can lift it wholesale. It wants roughly:
authenticate, fetch a serialized hand, iterate parsed events from the JSON stream, make
a call, play a card. Nothing clever. It will be documentation that happens to execute,
so it should read as an example first and be factored for testability second.

**The tests we will write.** They divide sharply by cost, so we should write them in
this order and decide after the first group whether the second is worth it. The cheap
group can use `live_server`, which already works here (`app/test_ui_playwright.py` uses
it); the streaming group cannot, for reasons below.

*Cheap: ordinary HTTP, no streaming.* These need only `requests`, and they behave like
every other test in the suite.

- Authenticate and fetch a serialized hand, asserting the documented shape.
- Make a call and play a card through the client, then assert the effect via a fresh
  `/serialized/hand/<pk>/`.
- Re-sync: let calls happen, then fetch the serialized hand and assert the client's view
  matches server truth. This is half of the recovery story, and the half that does not
  need a live stream.
- Play a hand to completion by polling `/serialized/hand/<pk>/` between actions. That
  demonstrates the real claim — somebody else could write one of these — without
  touching SSE at all, which is exactly how `cheating_bot` already operates.

*Expensive: needs a live stream.* Only these two require reading events as they arrive.

- Follow a hand: connect, have the server record a call, assert the client sees the
  event.
- Recover across a disconnect: read events, drop the connection mid-hand, let calls
  happen while away, reconnect, and assert the client catches up.

### The streaming tests will run against daphne, not `live_server`

`live_server` is WSGI-only, and not by pytest-django's choice: Django's
`LiveServerThread` hardcodes `server_class = ThreadedWSGIServer` and builds its app from
`WSGIHandler()` (`django/test/testcases.py:1735-1761`). django-eventstream yields async
iterables, so under `live_server` they reach us through an `async_to_sync` fallback,
which `pyproject.toml`'s `filterwarnings` already notes. That means a streaming test
run under `live_server` does not exercise the code path we ship, and can pass while
production breaks, or buffer instead of streaming and never yield the event it waits
for.

Django keeps the WSGI server because `LiveServerTestCase` predates ASGI, because an ASGI
live server would mean a third-party dependency, and above all because the fixture hands
the server thread the test's own database connection (`testcases.py:1754-1758`) so the
server sees uncommitted data and everything rolls back. That trick does not survive an
event loop. Channels ships `ChannelsLiveServerTestCase` to work around all of this,
which is good evidence the gap is real and widely felt.

We will spin daphne ourselves in a fixture instead. Daphne is already a dependency, we
already run it in development and production, and the tests already require Postgres and
Redis, so a server process is no new class of burden. What we get for it is the real
code path.

The tradeoffs and wrinkles we should expect:

- **No shared transaction.** A separate process cannot see our test's uncommitted data,
  so these tests need `django_db(transaction=True)` and committed fixtures. They will be
  slower and will tear down differently from the rest of the suite. This is the same
  price `ChannelsLiveServerTestCase` pays.
- **`test_settings.py` hardcodes the database name.** It sets `"NAME": "bridge"` with
  `TEST: {"NAME": "test_bridge"}`, so a daphne subprocess inheriting those settings would
  connect to the development database rather than the test one. We will need the name to
  come from the environment before the fixture can point daphne at `test_bridge`.
- **Hanging is the default failure mode.** A stream built to run forever, read by a test
  with no timeout, does not fail; it hangs, and under pytest-xdist it hangs quietly. The
  `pytest_sessionfinish` hook in `conftest.py` that force-exits because "live_server
  keeps database connections open and creates non-daemon threads that don't terminate
  cleanly" is evidence this area has bitten us before. Every streaming test needs an
  explicit read timeout and stopping condition from the first line, and the fixture needs
  a readiness poll on startup and a terminate-with-timeout on teardown.
- **Redis is load-bearing here.** `eventstream.py:29` branches on `EVENTSTREAM_REDIS`,
  which `base_settings.py` sets unconditionally, so delivery in these tests goes through
  a real Redis rather than anything in-memory.

None of that is token-expensive in itself. The cost is that failures in this area are
slow and opaque, and slow opaque iterations are what actually run up a bill. All of it
lands on the first streaming test; once one works, the second is a variation.

The cheap group gives us genuine contract coverage of the endpoint's shape and
semantics. The expensive group is the only thing that proves events actually arrive over
the wire. Both are worth having; only the first is obviously worth having *first*.
