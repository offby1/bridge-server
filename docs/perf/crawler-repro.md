# Reproducing the list-view crawler load (`project/app/manually_test_rate_limiting.py`)

Companion doc for `project/app/manually_test_rate_limiting.py`. That script
reproduces the crawler that made prod unresponsive on 2026-07-15, so you can
watch the failure happen on your laptop and experiment with fixes — and it
doubles as a manual test for the Caddy rate limit (below).

## Background: what took prod down

A crawler (`93.123.109.102`) spent ~90s (07:50–07:52) walking the sortable /
filterable list views — `/players/`, `/hand/`, `/board/` — following every
combination of **tournament filter × sort column × page number**. Each URL is
a distinct, uncached `prepop()`-with-count query.

Fired concurrently, they piled up faster than the single Daphne process could
execute sync views to completion. The binding constraint was the **asgiref
thread executor / GIL** that runs our synchronous Django views — not the
database. Requests stalled in that execution path, each holding an idle
Postgres connection open (`CONN_MAX_AGE=0` frees a connection only when the
request *finishes*, and these never did), so backends climbed toward the 200
cap as a *symptom*. The process then wedged holding ~162 connections open →
host unresponsive.

The decisive tell in the logs: even a trivial `GET /player/N/ => 302` redirect
— which does essentially no DB work — was taking 3+ seconds. Combined with the
metrics below (individual DB queries stayed ~0.5–2.5ms throughout), that rules
out slow SQL and DB saturation: the time was spent *waiting to run*, not
querying. Then Daphne killed 193 pending request tasks at once when the
container was restarted.

SSE connections played no part: the crawler only hit list views and never
requested any `/events/` URL, so it created zero SSE connections. See
`sse-connections.md` for why the (coincidentally equal) ~176 SSE setups in the
logs were unrelated to the ~176 Postgres backends measured below.

## Measured evidence (Prometheus)

Metrics from the outage window (2026-07-15 UTC; Prometheus at `hetz-bridge:9090`):

| Time | PG backends | req/s | p95 latency | avg DB query | DB q/s |
|---|---|---|---|---|---|
| 07:40–07:45 | 3–8 | 0.07 | 0.05s | ~0.6ms | 0.2 |
| 07:46:30–07:48 | 3–4 | 0.09 | **4.0s** | ~1.3ms | 13 |
| 07:49–07:51 | 3–7 | 0.1–0.3 | 0.05s | ~0.6ms | 0.2 |
| **07:52** | **49** | 0.9 | 0.41s | 2.5ms | 10 |
| **07:53** | **164** (peak 176) | — | — | — | — |
| 07:54–08:00 | ~162 (pinned) | *(django unscraped — process wedged)* | | | |

Read-out:

- **DB queries stayed fast (~0.5–2.5ms) the whole time** → Postgres was never
  the bottleneck.
- **Backends still exploded 6 → 176** → those connections were open but *idle*,
  held by requests stuck in the execution path (the same population as the 193
  killed tasks). Backend count is a *symptom* of the request pile-up, not a
  cause.
- **Peak 176 / 200 (88%)** → the cap was approached, not hit (no "too many
  clients" errors). But since stuck requests hold connections until they finish,
  a flood ~15% larger would have exhausted Postgres connections too — a latent
  second, DB-wide failure mode.
- A smaller precursor burst at 07:46–48 spiked p95 to 4s and recovered.
- The equal `176`s (SSE setups over 9h vs. peak PG backends) are coincidence:
  backends sat at 3–8 all morning *while* those SSE connections were being made,
  and only spiked with the crawler.

`PlayerListView` (`project/app/views/player.py:508`) is a django-tables2
`SingleTableMixin` + django-filter `FilterView`: every sortable column, filter,
and page number is a distinct crawlable URL — a combinatorial crawler trap.

## Quick start

Pool-exhaustion repro (no Caddy needed — you're stressing Daphne directly):

```bash
just runme                                              # local dev server on :9000
python3 project/app/manually_test_rate_limiting.py      # default: 20 workers, until Ctrl-C
```

For the **rate-limit** test you need Caddy in front — see "Testing the Caddy
rate limit" below.

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
   ASGI behavior faithfully, run the flood against a Docker stack (`just dev`
   locally, or `just mini`), which runs Daphne like prod.

## Fixes worth testing against it

(From the original diagnosis — use the script to measure before/after.)

- Rate-limit / block abusive IPs at Caddy (quickest stopgap).
- `robots.txt` + `nofollow` on sort/filter/pagination links; consider requiring
  login for the list views.
- **Bound request concurrency** so a pile-up can't run the process — and the
  Postgres connection count — to the edge (the latent 200-cap failure mode
  above). Unauthenticated list views are free ammunition for a crawler.
- Make the list queries cheaper — index the sort/filter columns, bound
  pagination. (Buys headroom, but doesn't remove the failure mode on its own.)

## Testing the Caddy rate limit

The per-IP rate limit lives at Caddy (`caddy/Caddyfile`, plugin built in via
`caddy/Dockerfile`), so you can only test it against a stack that actually runs
Caddy. **`just runme`, `just dev`, and `just dcu` do not** — Caddy is gated to
the `prod`/`beta` compose profiles, and the `dev` profile omits it (justfile:
"prod and beta get caddy + monitoring; dev doesn't"). The convenient option is
**`just mini`**, which deploys the `beta,monitoring` profile (Caddy *and*
Grafana/Prometheus) to the mac-mini context — and has no main-branch/clean-tree
guard, so it deploys this branch as-is. To verify:

1. Deploy this branch to the mini: `just mini`.
2. Aim the script at **the mini's Caddy hostname, not `:9000`** — hitting Daphne
   directly bypasses the edge and shows zero limiting (a misleading "pass"):

   ```bash
   python3 project/app/manually_test_rate_limiting.py \
       --base-url https://erics-mac-mini.tail571dc2.ts.net --insecure \
       --concurrency 20 --duration 30
   ```

   (`--insecure` because Caddy serves a `.ts.net` name with its internal CA, not
   a public cert.)

3. **Pass criterion:** accepted (2xx/3xx) responses plateau at the configured
   rate (~5/s for 50 events / 10s) while the rest come back **429**, and `err`
   stays 0 (Caddy sheds cleanly — no 5xx, no timeouts). Watch the `429/s` column
   and the `By status:` summary line. In the mini's Grafana, Postgres backends
   (`sum(pg_stat_database_numbackends)`) should stay flat — the flood never
   reaches the app.

Caveat: the limit keys on client IP, so running from one machine means the
`canary` shares the bucket and gets 429'd too (correct behavior). To see the
"other users unaffected" property, hit the app from a second IP (e.g. your
phone on cellular) while the flood runs.
