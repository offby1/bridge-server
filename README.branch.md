# Branch goal: two SSE connections per client, not six

## What we're doing

Collapse the seven per-channel `/events/...` endpoints into **two**: one shared stream
that every client gets, and one per-player stream carrying everything meant for that
authenticated player alone.

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

**One shared stream.** Channels that are identical for everyone, currently `lobby` and
`all-tables`. No per-viewer content, so nothing here needs the viewer's identity.

**One per-player stream.** Everything addressed to a single authenticated player:
their bot-checkbox, their private hand HTML, their chat channels, and the table
channel for whichever hand the page is showing. The client asks for one connection;
the server decides what belongs on it.

We don't need new machinery for the routing. `django_eventstream` already asks the
channel manager for a channel set when a URL doesn't hardcode one
(`eventrequest.py:60-66`), and we already have `app/channelmanager.py`. Each of the two
endpoints becomes a path with no `channels` kwarg, and `MyChannelManager` computes the
set from the request. Permission checks stay where they are, in `can_read_channel`.

Three things need attention:

- **Event types.** Every `send_event` call currently passes `"message"`, which works
  only because each channel has its own connection. Once several kinds of update share
  a socket, each needs a distinct event type so htmx's `sse-swap` and our JS listeners
  can tell them apart and target the right element.
- **The table channel is page-dependent.** A viewer can be looking at a hand that isn't
  their current one, so the per-player endpoint needs the hand as a parameter that
  `get_channels_for_request` reads from `view_kwargs`.
- **The channel set is fixed at connect time.** When a player's situation changes, for
  instance when they're seated at a new hand, the client has to re-subscribe.
  `django_eventstream` has `stream-reset` for exactly this, and `bridge-game.js`
  already listens for it.

## Not in scope

Bots reach `/events/player/json/<player_id>/` over the API. They aren't browsers and
aren't subject to the connection limit, so that endpoint can stay as it is.

`app/middleware/sse_stream_log.py` logs each stream's open, close, reason and duration,
plus a running count of open streams. It's how we found the problem and it's how we'll
verify the fix; keep it.
