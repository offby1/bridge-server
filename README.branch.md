# Branch goal: one SSE connection per browser, not six

## What we're doing

Collapse the browser's per-channel `/events/...` endpoints into **one**, whose channel
set the server computes per request. Leave the programmatic JSON endpoint alone, and
give both kinds of client an honest recovery story for events they miss.

## Why

Browsers allow only six concurrent HTTP/1.1 connections per origin, shared across tabs.
Today each SSE channel gets its own endpoint and therefore its own socket, and a
departed page's stream lingers for up to 70 seconds, because django-eventstream only
notices the client left when a keep-alive write fails. A few ordinary navigations
exhaust the budget, after which the browser silently queues every further request
instead of sending it. We measured one POST that spent 42 seconds waiting in Chrome's
queue and 82ms at the server.

Production terminates TLS at Caddy and so gets HTTP/2, which multiplexes and mostly
hides this. Development serves plain HTTP/1.1 and does not. One connection keeps us
clear either way, and it's tidier regardless of transport.

## The plan

**One browser endpoint.** `MyChannelManager.get_channels_for_request()` returns the
union of the shared channels (`lobby`, `all-tables`), the viewing player's private
channels (bot-checkbox, private hand HTML, chat), and the table channel for whichever
hand the page is showing.

We don't need new machinery for the routing. `django_eventstream` already asks the
channel manager for a channel set when a URL doesn't hardcode one
(`eventrequest.py:60-66`), and we already have `app/channelmanager.py`. The endpoint
becomes a path with no `channels` kwarg. Mixing scopes on one socket weakens nothing,
because `can_read_channel` still vets every channel individually.

**`/events/player/json/<player_id>/` stays as it is.** It's the interface a third party
would write a client against, it carries JSON rather than HTML fragments, and a
programmatic client isn't competing for a browser's six sockets. Consolidating it would
serve nobody.

### Why one browser endpoint and not two

Splitting into a public stream and a private one sounds tidy, but it doesn't reduce
anything today: `can_read_channel` returns `False` for anyone without a player
(`channelmanager.py:16-25`), so anonymous visitors read nothing at all. Every client
that reads anything is authenticated and would therefore hold both connections, which
is two sockets per tab where one would do.

We do want unauthenticated users to observe games in progress some day. When that
happens, some channels become readable without a player and a second public endpoint
starts earning its socket. That's a change to `can_read_channel` first; the split
follows from it rather than preceding it.

### Three things need attention

- **Event types.** Every `send_event` call currently passes `"message"`, which works
  only because each channel has its own connection. Once several kinds of update share
  a socket, each needs a distinct event type so htmx's `sse-swap` and our JS listeners
  can tell them apart and target the right element. This is the bulk of the work.
- **The table channel is page-dependent.** A viewer can be looking at a hand that isn't
  their current one, so the endpoint needs the hand as a parameter that
  `get_channels_for_request` reads from `view_kwargs`.
- **The channel set is bound at connect time**, and nothing can add a channel to a live
  connection. To pick up a channel it doesn't have, the client must close and reopen
  the `EventSource`. A page navigation does that for free; anything that changes a
  player's situation without a navigation needs to re-dial deliberately.

## Recovery: re-sync from truth, not replay

When a client misses events, it re-reads current state rather than asking for the
events it missed. The browser already works this way in places: `bridge-game.js:76-80`
reloads the page outright on a phase transition instead of patching the DOM. API
clients get the same deal through `/serialized/hand/<pk>/` (`app/urls.py:45`).

This is a deliberate choice not to persist events, and it is worth recording why,
because the history reads the other way at a glance:

- **2025-06-04, `0bd4455f`** (perf branch) disabled persistence as a performance
  experiment, in the middle of a run of OOM and ulimit firefighting.
- **2025-06-06, `94bce2af`** restored it, because "we won't find half of our tables just
  sitting there, because one of the bots missed an event."
- **2025-06-30, `86677f9b`** replaced `EVENTSTREAM_STORAGE_CLASS` with
  `EVENTSTREAM_REDIS` while pulling Redis in. Those settings control different
  subsystems: the first is persistence, the second is the pub/sub transport. Persistence
  has been off ever since, apparently by accident.

The 2025-06-06 reason no longer applies. Nothing that advances a game reads SSE any
more: `docker-compose.yaml:76` runs `cheating_bot`, a single process that polls the
database on behalf of every bot player and contains no SSE code at all. A browser that
misses events shows a stale page, which a reload fixes; it doesn't stall a hand.

So persistence stays off, and `stream-reset` stays dead. `app/test_stream_reset.py`
records that: one test pins the storage-free behaviour and fails the day anyone enables
storage, and the rest show what the mechanism would do if we did.

**The catch.** A reconnect carries no notification that anything was missed, so
reacting to reconnects is all we have, and today streams re-dial about once a minute.
Reloading the page every minute during an auction would be worse than the staleness.
Two things make it affordable, and they compose: consolidation cuts four connections to
one and so cuts reconnects proportionally, and re-fetching the hand fragment over htmx
costs no scroll position and no focus, which matters when the thing being interrupted
is a bidding box.

## A reference client that is also the contract tests

Keeping the JSON endpoint means owing its consumers a working interface, and nothing
outside `test_hand_events.py:44` and `test_hand.py:305` touches `player:json:*` today.
Those assert that events are *sent*, not that a client can follow a hand from them. The
old per-player API bot used to keep the endpoint honest, and it's gone.

So write one client and use it twice: as the example a third party reads, and as the
thing our tests drive.

**The client.** A small module depending only on `requests` and `sseclient`, both
already in `pyproject.toml` and both currently unused, so this adds nothing and a third
party can lift it wholesale. It wants roughly: authenticate, fetch a serialized hand,
iterate parsed events from the JSON stream, make a call, play a card. Nothing clever.
It's documentation that happens to execute, so it should read as an example first and
be factored for testability second.

**The tests.** Driven against `live_server`, which already works here
(`app/test_ui_playwright.py` uses it):

- Authenticate and fetch a serialized hand, asserting the documented shape.
- Follow a hand: connect, have the server record a call, assert the client sees it.
- Recover: disconnect mid-hand, let calls happen while away, reconnect, re-fetch, and
  assert the client's view matches server truth. This is the test that proves the
  recovery story we're documenting, and it's the one we have never exercised.
- Play a hand to completion through the client, which is the real claim: that somebody
  else could write one of these.

Expect friction. django-eventstream yields async iterables, `live_server` is WSGI and
falls back to `async_to_sync` (see the `filterwarnings` entries in `pyproject.toml`),
and a test that reads a stream designed to run forever needs a deliberate stopping
condition. Budget for that rather than being surprised by it.
