# Branch goal: one SSE connection per client, not six

## What we're doing

Collapse the seven per-channel `/events/...` endpoints into **one**, whose channel set
the server computes per request.

## Why

Browsers allow only six concurrent HTTP/1.1 connections per origin, shared across
tabs. Today each SSE channel gets its own endpoint and therefore its own socket, and a
departed page's stream lingers for up to 70 seconds because django-eventstream only
notices the client left when a keep-alive write fails. A few ordinary navigations
exhaust the budget, after which the browser silently queues every further request
instead of sending it. We measured one POST that spent 42 seconds waiting in Chrome's
queue and 82ms at the server.

Production terminates TLS at Caddy and so gets HTTP/2, which multiplexes and mostly
hides this. Development serves plain HTTP/1.1 and does not. Two connections keep us
comfortably clear of the limit either way, and collapsing seven endpoints into two is
tidier regardless of transport.

## The plan

One endpoint. `MyChannelManager.get_channels_for_request()` returns the union of the
shared channels (`lobby`, `all-tables`), that player's private channels (bot-checkbox,
private hand HTML, chat), and the table channel for whichever hand the page is showing.

We don't need new machinery for the routing. `django_eventstream` already asks the
channel manager for a channel set when a URL doesn't hardcode one
(`eventrequest.py:60-66`), and we already have `app/channelmanager.py`. The endpoint
becomes a path with no `channels` kwarg. Mixing scopes on one socket weakens nothing,
because `can_read_channel` still vets every channel individually.

### Why one and not two

Splitting into a public stream and a private one sounds tidy, but it doesn't reduce
anything today: `can_read_channel` returns `False` for anyone without a player
(`channelmanager.py:16-25`), so anonymous visitors read nothing at all. Every client
that reads anything is authenticated and would therefore hold both connections, which
is two sockets per tab where one would do. The constraint is sockets per client, not
endpoints per permission class.

We do want unauthenticated users to observe games in progress some day. When that
happens, some channels become readable without a player, and a second public endpoint
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
  connection. To pick up a channel it doesn't have, for instance after being seated at
  a new hand, the client must close and reopen the `EventSource`. A page navigation
  does that for free; anything that changes a player's situation without a navigation
  needs to re-dial deliberately.

## `stream-reset`, and why we don't trust it yet

`stream-reset` is not a subscription-management mechanism, which is easy to assume from
the name. `eventstream.py:132-147` raises it when a client reconnects with a
`Last-Event-ID` whose events have already aged out of storage: django-eventstream
cannot replay the gap, so it sets `reset = True` and `eventresponse.py:36-39` emits a
`stream-reset` event naming the affected channels. It means "you missed events, I can't
tell you which, re-sync from scratch."

Today it never fires at all. `EVENTSTREAM_STORAGE_CLASS` is unset, so `get_storage()`
returns `None` and `eventstream.py:124` skips the branch that would raise a reset. With
no storage there is also no replay: a reconnecting client's `Last-Event-ID` is parsed
and then effectively ignored. Whatever happened while it was disconnected is simply
gone, and nothing tells it so. The gap is silent by construction, which is worse than a
reset we mishandle.

And we would mishandle it. `bridge-game.js:38-41` and `bridge-game.js:54-57` parse the
payload and write it to the console; nothing re-syncs. Between the two, a client that
misses events stays stale until the viewer reloads, which is very likely one reason a
hand page can sit showing no calls while the bot plays on.

Enabling storage is therefore a prerequisite, not a detail. `app/test_stream_reset.py`
covers both sides of that step: one test pins the current storage-free behaviour and
will fail when we turn storage on, and the rest prove the mechanism works once we do.

Consolidating onto one connection raises the stakes: a single reset now means every
channel that client cares about may be stale, not just one.

So this branch treats `stream-reset` as work in its own right, and it doesn't ship
until automated tests cover it:

- **Server side.** Connect to the endpoint with a stale or bogus `Last-Event-ID` and
  assert the stream emits `event: stream-reset` naming the expected channels. This
  needs no timing games; an id that never existed takes the same code path as one that
  expired.
- **Client side.** The handler must re-fetch state rather than log. A Playwright test
  should force a reset and assert the DOM catches up to the true server state.
- **End to end.** Drop events on the floor while a client is connected, then confirm
  the client notices and recovers. This is the case we most want to be confident in,
  because it is the one nobody exercises by hand.

## Not in scope

Bots reach `/events/player/json/<player_id>/` over the API. They aren't browsers and
aren't subject to the connection limit, so that endpoint can stay as it is.

`app/middleware/sse_stream_log.py` logs each stream's open, close, reason and duration,
plus a running count of open streams. It's how we found the problem and it's how we'll
verify the fix; keep it.
