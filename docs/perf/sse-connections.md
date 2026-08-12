# SSE connections: a red herring for the outage (plus efficiency notes)

**Conclusion up front: SSE connections had nothing to do with the 2026-07-15
outage.** The crawler never touched `/events/`, and the Postgres-backend spike
that *did* happen was stuck list-view requests, not SSE streams (measured — see
`crawler-repro.md`). This doc exists because SSE was initially, wrongly,
suspected; it records (a) what an SSE connection actually is, so the confusion
doesn't recur, and (b) some genuine connection-count hygiene worth doing
independently of the outage.

Companion to `crawler-repro.md`. Written during the 2026-07-15 investigation, so the
measurements below describe the SSE arrangement *as it was then*: one endpoint per channel,
four connections for a hand page. That has since been consolidated to one connection per
page — see "What we did about it" at the end, and `docs/README.sse.md` for the design that
replaced it.

## What we mean by an "SSE connection" (precise)

An **SSE connection is a long-lived HTTP connection from a *browser* to our
*web server* (Daphne)** — it is **not** a connection to Postgres.

Server-Sent Events work like this: the browser runs
`new EventSource('/events/…/')`, which issues an ordinary HTTP GET. Instead of
replying and closing, the server holds the TCP socket open and dribbles
`data: {…}\n\n` chunks down it as game state changes. So one SSE connection =

```
browser tab  ⇄  Caddy (TLS :443)  ⇄  Daphne / ASGI (:9000)
```

one persistent HTTP/TCP socket, alive for as long as the page is open (and
auto-reopened by `ReconnectingEventSource` whenever the network drops).

### The 200 cap is a *different* resource

The `--max_connections=200` you remember (`docker-compose.yaml:124`) is a
**Postgres** server setting. It caps connections on this leg:

```
Daphne / Django  ⇄  Postgres (:5432)
```

Postgres caps connections because **each connection is a separate backend OS
process** on the database server, each holding its own memory (work_mem, temp
buffers) — Postgres does not pool or multiplex them internally. Too many and the
DB server thrashes or runs out of RAM. Default is 100; we raised it to 200 to
leave headroom for many simultaneous web requests.

### How the two legs relate (this is the subtle part)

An open SSE connection does **not** hold a Postgres connection for its lifetime.
`CONN_MAX_AGE` is unset in our settings → Django's default of `0` → a DB
connection is opened and **closed per request-burst**. An SSE stream only touches
Postgres briefly: once at subscribe time (`MyChannelManager.can_read_channel`,
`app/channelmanager.py`) and again each time an event is sent. Between those it
is idle, parked on a Redis pub/sub subscription (`EVENTSTREAM_REDIS`,
`base_settings.py:137`), holding **no** DB connection.

So: **176 SSE connections do not mean 176 Postgres connections.** They are
bounded by Daphne / OS file descriptors / memory, not by the 200. The 200 is
consumed by *concurrent request-bursts* (ordinary page views, SSE setup/send,
and — during the outage — the crawler's flood of list-view queries).

### Confirmed by metrics (this was the red herring)

My first pass claimed the SSE connections "thinned the pool" during the crawler
flood. Prometheus disproves it:

- **Postgres backends sat at 3–8 all morning**, including while those SSE
  connections were being established, and only spiked (to a peak of 176 / 200)
  when the crawler hit at 07:52. So the ~176 SSE *setups over 9 hours* and the
  ~176 *concurrent Postgres backends* at the peak are numerically equal by
  **coincidence** — different things at different times.
- **Zero** SSE connections were even initiated during the 07:50–07:53 flood
  window (`grep 'GET:/events' … | grep -c 'T07:5[0-3]'` → 0).
- The backend spike was stuck *list-view request* connections, not SSE (the DB
  queries stayed ~0.5–2.5ms; connections were held open because the requests
  couldn't finish). Full timeline in `crawler-repro.md`.

Two facts made SSE look guilty in the logs: (1) there happened to be 176
`/events/` lines, and (2) `RequestLoggingMiddleware` (`simple_access_log.py`)
times only view *setup* for a streaming response — every `/events/` line reads
2–30ms, which is setup time, not the connection's true lifetime. Neither
implies any role in the outage. The SSE efficiency notes below are separate
hygiene.

## The three questions

### 1. Where did the 176 come from?

Not 176 browsers — just **two logged-in users** (`edh`, `905479`) on T-Mobile
mobile IPs (`172.56.x`) over a ~9-hour window. The count is inflated because:

- **`base.html:40` subscribes the `bot-checkbox` channel on *every*
  authenticated page** — game page or not. So every navigation opens one.
- A single hand page opens **four separate connections**, one per channel,
  because each is its own `/events/…` URL route (`urls.py`, six
  `include(django_eventstream.urls)` entries).
- `ReconnectingEventSource` reopens on every mobile-network hiccup, and
  `window.location.reload()` on contract/score transitions (`bridge-game.js`)
  tears down and reopens all streams. Navigations + reconnects + reloads
  multiply the setup count.

The 176 is therefore a tally of connection *setups over 9 hours*, not a
concurrent count (which the logs can't tell us — see the timing note above).

### 2. What purpose does each serve?

| Channel | Setups | Purpose |
|---|---|---|
| `player/bot-checkbox/{pk}` | 82 | keep the "let a bot play for me" checkbox in sync, sitewide |
| `table/html/{hand}` | 44 | auction / trick-count / contract updates for the table |
| `player/html/hand/{pk}` | 32 | private hand + bidding-box updates |
| `chat/player-to-player/{a_b}` | 18 | encrypted player-to-player chat |

### 3. Can we prune more efficiently?

Pruning *faster* is not the lever — idle SSE streams don't pin DB connections
(`CONN_MAX_AGE=0`), and browsers/Daphne already close them on
navigate/disconnect. The win is **opening fewer**.

## What we did about it

The consolidation this section originally listed as a TODO has landed. `docs/README.sse.md`
describes the result; in terms of the items as they were written:

- **Consolidate per-player channels onto one connection — done, and further than
  proposed.** There is now exactly one browser endpoint, `/events/all/`, which names no
  channels at all: `MyChannelManager.get_channels_for_request` works out the set from the
  session plus `?hand=` and `?chat=`. So a hand page opens one connection, not four.
- **Stop subscribing `bot-checkbox` sitewide — done differently.** The checkbox still
  carries its `sse-swap`, but the *connection* is what got gated: a page where nothing can
  change overrides the `sse_connection` block to nothing and spends no connection at all.
  Only three pages keep one — the interactive hand, a read-only hand still being played,
  and the player detail page, which has chat. `app/test_sse_opt_out.py` enforces the split
  in both directions. The trade-off: on an opted-out page the navbar checkbox is correct at
  page load and then stops updating by itself.
- **Reduce reload-driven churn — not done, and deliberately.** `base.html` now reloads the
  page when the connection *reopens*, which is more reloading, not less. It is affordable
  precisely because of the consolidation: a live tab holds one connection for as long as it
  is open, instead of four re-dialling about once a minute. Two guards keep it in check (the
  first `open` doesn't count, and a page younger than ten seconds doesn't reload). If
  interrupting somebody's bidding box turns out to annoy, re-fetching the hand fragment over
  htmx is the upgrade.
- **Leave reconnect churn alone — still the right call.** The client does now hand the
  socket back on `pagehide` rather than leaving the server to notice a minute later.

Note: none of this addressed the outage — that was crawler rate-limiting
(see `crawler-repro.md`). This was capacity hygiene that buys headroom under load.

The numbers earlier in this document are the *pre-consolidation* measurements, kept because
they are what motivated the change. In particular the four-row channel table describes the
four endpoints a hand page used to open; there is one now.
