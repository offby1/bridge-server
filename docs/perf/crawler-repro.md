# Reproducing the list-view crawler load (`crawler_repro.py`)

Companion doc for `crawler_repro.py` (repo root). That script reproduces the
crawler that made prod unresponsive on 2026-07-15, so you can watch the
failure happen on your laptop and experiment with fixes.

## Background: what took prod down

A crawler (`93.123.109.102`) spent ~90s (07:50–07:52) walking the sortable /
filterable list views — `/players/`, `/hand/`, `/board/` — following every
combination of **tournament filter × sort column × page number**. Each URL is
a distinct, uncached `prepop()`-with-count query. Fired concurrently they
saturated Daphne's sync-view thread pool (already thinned by ~176 long-lived
SSE `/events/` connections), and latency climbed monotonically from ~63ms to
~3600ms.

The decisive tell in the logs: even a trivial `GET /player/N/ => 302` redirect
— which does essentially no DB work — was taking 3+ seconds. That's
**worker/connection-pool exhaustion**, not slow SQL. Then Daphne killed 193
pending request tasks at once when the container was restarted.

`PlayerListView` (`project/app/views/player.py:508`) is a django-tables2
`SingleTableMixin` + django-filter `FilterView`: every sortable column, filter,
and page number is a distinct crawlable URL — a combinatorial crawler trap.

## Quick start

```bash
just runme                       # start local dev server on :9000 first
python3 crawler_repro.py         # default: 20 workers, runs until Ctrl-C
```

Pure Python 3 stdlib — no install, no venv. **Never aim it at prod.**

Each second it prints throughput and latency percentiles for the flood, plus
the latency of a low-rate **canary** probe (`/player/1/`, a 302 that does ~no
DB work). When the canary climbs into seconds — and eventually times out
(`err` rises) — you've reproduced the prod signature: an innocent request
starves because the flood ate the pool.

```
 elapsed   req/s    done   err     p50     p95      max   canary
      5s      42     210     0    380m    910m    1400m       120ms [302]
     10s      28     480     0    690m   1800m    3100m      1450ms [302] !!
```

## Ways to use it / things to explore

- **Find the cliff.** Run with `--concurrency 5`, then `20`, then `60`, and
  watch the canary go from flat to seconds. This is the single best knob for
  *feeling* the pool exhaustion — the whole point of the exercise.
- **Auto-stop** a run with `--duration 60` instead of Ctrl-C.
- **Match your local data.** If your DB has fewer tournaments, shrink the URL
  space to real rows: `--tournaments 1-10 --pages 1-5`. (Filters that match
  nothing are cheap and won't show the problem.)
- **Point at beta, not prod:**
  `--base-url https://beta.bridge.offby1.info --insecure`.
- **Change the canary** with `--canary-path` / `--canary-interval` to measure a
  different "innocent" endpoint's degradation.

## Two caveats that matter

1. **Closed-loop, not open-loop.** Workers wait for each response, so the load
   self-throttles and won't spiral your laptop — but that also *under*-represents
   a real crawler's unbounded pileup. Crank `--concurrency` to compensate;
   that's the intended way to explore the cliff.
2. **Dev server ≠ prod server.** `just runme` uses Django's dev server, not
   Daphne — the thread/connection-pool dynamics differ. To reproduce the actual
   ASGI behavior faithfully, run the flood against `just dcu` (the Docker stack
   runs Daphne like prod).

## Fixes worth testing against it

(From the original diagnosis — use the script to measure before/after.)

- Rate-limit / block abusive IPs at Caddy (quickest stopgap).
- `robots.txt` + `nofollow` on sort/filter/pagination links; consider requiring
  login for the list views.
- Bound the exposure: the SSE connections and the sync-view thread pool compete
  for the same headroom; unauthenticated list views are free ammunition.
- Make the list queries cheaper — index the sort/filter columns, bound
  pagination.
