# Server-sent events: how the browser gets told things

This is about the *browser's* connection. The interface third parties write clients
against is a separate thing, documented in `README.api.md`.

## One connection per page, and why it matters

Browsers allow only six concurrent HTTP/1.1 connections per origin, shared across every
tab. An SSE stream holds one of those for as long as it lives, so the six-connection
budget is really a budget for how many streams a person can have open at once.

We used to spend it recklessly: one endpoint per channel meant a hand page opened four
connections, and each page you navigated away from held its connection for another 55 to
70 seconds. django-eventstream only discovers a departed client when a keep-alive write
fails, and it writes every 20 seconds. A handful of ordinary navigations therefore
exhausted the budget, after which the browser queued every subsequent request without
sending it, silently. We measured a POST that spent 42 seconds waiting in Chrome's queue
and 82 milliseconds at the server.

So: **one connection per page.** Adding an endpoint, or opening a second `EventSource`,
takes that away. Don't.

Production terminates TLS at Caddy and so speaks HTTP/2, which multiplexes and would
mostly hide the problem. Development serves plain HTTP/1.1 and does not. One connection
is correct on both.

## How the one connection works

`<body>` in `base.html` owns it. htmx's SSE extension attaches every descendant carrying
`sse-swap` to the nearest ancestor that owns a connection, so the navbar checkbox, the
chat log and the hand all share the same socket without knowing about each other.

`base.html` opens it before htmx gets the chance and keeps the object in
`window.bridgeEventSource`, for two reasons: we want `ReconnectingEventSource` rather
than the bare `EventSource` htmx would construct, and `bridge-game.js` needs a reference
so it can listen on the same socket instead of opening more.

Pages say which channels they need by overriding the `sse_channels_query` block, which
lands in the URL as `?hand=` or `?chat=`. Keep that block on one line: its content is
interpolated into an attribute, so a formatter that spreads it across lines injects
whitespace into the query string. `app/test_sse_connect_url.py` guards against exactly
that.

`MyChannelManager.get_channels_for_request` turns the request into a channel set. It
validates those parameters rather than trusting them, because `can_read_channel` used to
allow any name it didn't recognise, which turned two malformed parameters into two bugs
in a single day. It denies by default now, and `app/test_consolidated_channels.py` keeps
both halves honest.

## Event names

Every kind of update has its own name, in `SSEEventTypes` (`app/sse_events.py`). This is
forced by the consolidation: when each channel had a connection to itself, the channel
implied the meaning and everything could travel as `"message"`. Sharing a socket means
the name is the only thing distinguishing a bidding-box update from a chat message.

Those names are a contract between Python and JavaScript that no type checker sees.
Rename one end and the other goes quiet, with no error and no failed request.
`app/test_sse_event_types.py` checks that the browser subscribes to what the server
sends.

## Recovery: re-read, don't replay

We keep no event history. `EVENTSTREAM_STORAGE_CLASS` is unset, deliberately — see the
comment in `base_settings.py`, which explains why the git history looks like it says
otherwise. Consequences worth knowing:

- A reconnecting client cannot replay what it missed, and nothing tells it that it
  missed anything.
- django-eventstream's `stream-reset` can never fire, so the handlers in
  `bridge-game.js` only log. `app/test_stream_reset.py` records this, and will fail the
  day somebody enables storage.

The recovery is therefore to re-read current state. `base.html` reloads the page when
the connection reopens after having been open before. Two guards: the first `open` is
the initial connection rather than a reconnect, and a page younger than ten seconds
doesn't reload, which both avoids pointless work and limits us to one reload per ten
seconds if the server is flapping, since each reload restarts that clock.

Reloading is affordable only because of the consolidation. When a page held four
connections and re-dialled about once a minute, reloading on reconnect would have been
worse than the staleness. A live tab now holds one connection for as long as it is open.
If interrupting somebody's bidding box turns out to annoy, re-fetching the hand fragment
over htmx is the upgrade; it keeps scroll position and focus.

The client also hands the socket back on `pagehide`, rather than leaving the server to
notice a minute later. `pagehide` rather than `beforeunload`, because it fires on mobile
Safari and on the back/forward cache path. A page restored from that cache reloads,
since its listeners are bound to a connection we closed.

## When something isn't updating

`app/middleware/sse_stream_log.py` logs every stream's open and close, with a reason, a
duration, and a count of how many are open. Start there. A page should show one
`/events/all/...` open, plus `/__reload__/events/` in development.

Other things worth knowing when you're staring at this:

- **`send_event` logs in whichever process calls it.** The bot writes to `bot`'s log,
  not `django`'s. Grepping the wrong container makes it look like nothing is being sent.
- **`RequestLoggingMiddleware` starts its clock at its own position in the chain**, so
  its `ms=` figure excludes every middleware listed before it in `base_settings.py`, and
  it never sees responses those outer middlewares generate. A request can be slow, or
  refused, without that log showing it.
- **In DevTools, tick "Preserve log" before clicking**: a form POST is a navigation and
  clears the Network panel otherwise. Time under "Stalled" or "Queueing" means the
  browser held the request; time under "Waiting (TTFB)" means the server did.
- **`lsof -nP -iTCP:9000 | grep -v LISTEN`** counts the browser's connections against
  its six.
- **Restarting the server produces several page loads, not one.** `just dev` recreates
  containers in stages, so there is more than one reconnect, and `django_browser_reload`
  reloads on reconnect as well. That is not a loop. Browser-reload is development-only,
  so in production our own handler is the only one.
