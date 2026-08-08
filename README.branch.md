# Branch goal: one SSE connection per browser, not six

**Status: nothing below has been built yet.** The only code this branch has landed so
far is `app/middleware/sse_stream_log.py` (diagnostics), `app/test_stream_reset.py`
(characterization tests), and a narrowing of the bot-checkbox subscription in
`base.html`. Everything else is intent.

Throughout this document, "today" and "currently" describe the repository as it stands;
"we will" and "this branch will" describe work not yet done. Where a sentence could be
read either way, it's a bug in the document.

## What this branch will do

This branch will collapse the browser's per-channel `/events/...` endpoints into one,
whose channel set the server computes per request. It will leave the programmatic JSON
endpoint as it is, and it will give both kinds of client a recovery story for events
they miss.

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

## The plan

**One browser endpoint.** We will add an endpoint whose URL hardcodes no channels, and
teach `MyChannelManager.get_channels_for_request()` to return the union of the shared
channels (`lobby`, `all-tables`), the viewing player's private channels (bot-checkbox,
private hand HTML, chat), and the table channel for whichever hand the page is showing.

This needs no new machinery. `django_eventstream` already asks the channel manager for
a channel set when a URL doesn't hardcode one (`eventrequest.py:60-66`), and
`app/channelmanager.py` already exists. Mixing scopes on one socket will weaken nothing,
because `can_read_channel` vets every channel individually today and will continue to.

**We will not touch `/events/player/json/<player_id>/`.** It is the interface a third
party would write a client against, it carries JSON rather than HTML fragments, and a
programmatic client does not compete for a browser's six sockets. Consolidating it would
serve nobody.

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

### Three things will need attention

- **Event types.** Every `send_event` call passes `"message"` today, which works only
  because each channel has its own connection. Once several kinds of update share a
  socket, each will need a distinct event type, so that htmx's `sse-swap` and our JS
  listeners can tell them apart and target the right element. We expect this to be the
  bulk of the work.
- **The table channel is page-dependent.** A viewer can be looking at a hand that isn't
  their current one, so the new endpoint will need the hand as a parameter that
  `get_channels_for_request` reads from `view_kwargs`.
- **The channel set is bound at connect time.** Nothing can add a channel to a live
  connection, today or after this branch. To pick up a channel it lacks, a client must
  close and reopen its `EventSource`. A page navigation does that for free; anything
  that changes a player's situation without a navigation will have to re-dial
  deliberately.

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

**The catch.** A reconnect carries no notification that anything was missed, so reacting
to reconnects is all we will have, and today streams re-dial about once a minute.
Reloading the page every minute during an auction would be worse than the staleness.
Two things would make it affordable, and they compose: consolidation cuts four
connections to one and so cuts reconnects proportionally, and re-fetching the hand
fragment over htmx costs no scroll position and no focus, which matters when the thing
being interrupted is a bidding box.

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

**The tests we will write**, driven against `live_server`, which already works here
(`app/test_ui_playwright.py` uses it):

- Authenticate and fetch a serialized hand, asserting the documented shape.
- Follow a hand: connect, have the server record a call, assert the client sees it.
- Recover: disconnect mid-hand, let calls happen while away, reconnect, re-fetch, and
  assert the client's view matches server truth. This is the test that would prove the
  recovery story above, and it is the one we have never exercised.
- Play a hand to completion through the client, which is the real claim: that somebody
  else could write one of these.

Expect friction. django-eventstream yields async iterables, `live_server` is WSGI and
falls back to `async_to_sync` (see the `filterwarnings` entries in `pyproject.toml`),
and a test that reads a stream designed to run forever needs a deliberate stopping
condition. Budget for that rather than being surprised by it.
