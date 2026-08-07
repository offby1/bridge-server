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

## Second outage: the distributed flood (2026-08-04)

The per-IP rate limit (below) stopped the single-IP crawler. Three weeks later
the site fell over again — same wedge signature — *despite* the fix, because the
flood was **distributed**:

- **24,391 distinct source IPs** hit the list views, each making only **2–4
  requests** (max 4 across a two-week log). No IP came near the 5 req/s per-IP
  limit, so Caddy had nothing to reject — a per-IP bucket is useless when every
  client makes a handful of requests and leaves. (One IP, `93.123.109.10`, was
  in the original attacker's `/24` — plausibly the same actor gone distributed.)
- Same mechanism as 2026-07-15: list-view requests piled up in Daphne's
  execution path — ~100 stuck in-flight at the restart (84 `/players/`, 7
  `/board/`, 6 `/hand/`), latencies 44ms → 27s, no app errors, no DB-connection
  exhaustion. With Caddy in front it surfaced as **502 Bad Gateway** (Caddy's
  upstream stopped answering) rather than a raw wedge.

**Lesson: a per-IP limit defends against a single-IP flood; a distributed
botnet needs an *aggregate* cap.**

### Capacity, measured (beta = cpx21, same as prod)

To size an aggregate cap you need the throughput ceiling. Measured with an `ab`
concurrency ramp straight at Daphne (`127.0.0.1:9000`, `X-Forwarded-Proto:
https`, bypassing Caddy):

| endpoint | ceiling | shape |
|---|---|---|
| list view (`/players/?tournament=…`) | **~40 req/s** | plateaus at concurrency **2**; beyond that only latency grows — GIL-bound |
| cheap 302 (`/player/1/`) | **~90 req/s** | peaks at c=8, then *congestion-collapses* (72 → 51 → 19/s as concurrency climbs) — every request pays the full middleware stack under the GIL |

For scale, real legit load: **median 3 req/min (0.05/s); busiest minute in two
weeks 3.5/s** — ~1000× below capacity, so there's huge room to cap aggressively
without touching real users.

### The fix: tiered rate limits (`caddy/Caddyfile`)

Three zones, each shedding at the edge as `429` before a request reaches Daphne.
Rule of thumb: **measure the ceiling, halve it.**

| zone | scope | limit | why |
|---|---|---|---|
| `per_ip` | one client IP | 5/s (50 / 10s) | single-IP flood; keeps one IP from eating the shared budgets |
| `list_views` | `/players* /board* /hand* /tournament*`, aggregate | 20/s | ½ the ~40/s list-view ceiling |
| `whole_site` | everything, aggregate | 45/s | ½ the ~90/s cheap-request ceiling — backstop for a pivot to any other endpoint |

Why three and not one: a single site-wide 20/s cap would `429` legitimate
page-load bursts (a page load = HTML + several static files + `tz_detect` + an
SSE connect); a single *loose* cap wouldn't protect the fragile ~40/s list
views. So — a tight cap on the expensive paths, a looser backstop on everything.
Deployed and verified live on beta (2026-08); full before/after A/B in
[`rate-limit-ab-validation.md`](rate-limit-ab-validation.md).

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

## Caveats that matter

1. **Closed-loop, not open-loop.** Workers wait for each response, so the load
   self-throttles and won't spiral your laptop — but that also *under*-represents
   a real crawler's unbounded pileup. Crank `--concurrency` to compensate — but
   see caveat 3: over a remote/tailscale path the *path*, not `--concurrency`, is
   the limit.
2. **Dev server ≠ prod server.** `just runme` uses Django's dev server, not
   Daphne — the thread/connection-pool dynamics differ. To reproduce the actual
   ASGI behavior faithfully, run the flood against a Docker stack (`just dev`
   locally, or `just mini`), which runs Daphne like prod.
3. **This tester over `tailscale serve` (or any single remote client) cannot
   saturate Daphne.** Measured on the mini: a 200-thread flood from a laptop
   through `tailscale serve` (:443 → django) left Postgres backends idle at **8**
   while the client saw 2–8s latencies — the load never arrived. The throttle is
   the `tailscale serve` proxy plus a single laptop driving 200 concurrent HTTPS
   through CPython (the GIL + a full TLS handshake per request cap real client
   concurrency). Don't chase `backends=8`: it means the path, not Daphne, is the
   bottleneck. To actually reproduce **backend saturation**, run a real
   concurrent load tool *near* the server, straight at Daphne:

   ```bash
   # on the mini, bypassing tailscale AND Caddy:
   ulimit -n 8192
   ab -t 20 -c 150 -H "X-Forwarded-Proto: https" \
      "http://127.0.0.1:9000/players/?tournament__display_number=1"
   ```

   With that, backends climb 8 → ~100 and p95 latency hits several seconds — the
   outage signature. Gotchas: `X-Forwarded-Proto: https` is required (else
   `SECURE_SSL_REDIRECT` 301s every request to a cheap no-DB redirect and nothing
   saturates); on macOS use `127.0.0.1`, not `localhost` (`ab` fails with
   `apr_socket_connect: Invalid argument`); and raise the default 256 fd limit.
   The Python tester over tailscale is fine for watching **Caddy shed load**
   (429s) — just not for saturating Daphne.

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

> To *prove the fix works* (reproduce the blackout on `main`, then show it gone
> on this branch), follow the A/B procedure in
> [`rate-limit-ab-validation.md`](rate-limit-ab-validation.md). The quick check
> below just confirms the limiter is wired up and shedding load.

The per-IP rate limit lives at Caddy (`caddy/Caddyfile`, plugin built in via
`caddy/Dockerfile`), so you can only test it against a stack that actually runs
Caddy. **`just runme`, `just dev`, and `just dcu` do not** — Caddy is gated to
the `prod`/`beta` compose profiles, and the `dev` profile omits it (justfile:
"prod and beta get caddy + monitoring; dev doesn't"). The convenient option is
**`just mini`**, which deploys the `beta,monitoring` profile (Caddy *and*
Grafana/Prometheus) to the mac-mini context — and has no main-branch/clean-tree
guard, so it deploys this branch as-is. To verify:

1. Deploy this branch to the mini: `just mini`. (As of the `[merge to main]`
   `_deploy` fix, this starts Caddy itself; older revisions relied on Caddy
   already running and silently didn't start it on a fresh host.) Make sure
   ports 80 and 443 are free on the mini first — e.g. turn off any
   `tailscale funnel`/`serve` bound to 443, or Caddy's port bind will fail.

2. **Give Caddy a cert it can actually serve — the `.ts.net` gotcha.** Caddy
   can't get a public Let's Encrypt cert for a `.ts.net` name and won't
   self-sign a public-looking TLD, so out of the box the TLS handshake fails
   server-side (`curl` shows `tlsv1 alert internal error`) and *every* request
   in the script comes back status `0`: you'll see `err` == total and **no
   429s** — a non-result, not a limiter failure. Fix it for the test with a
   **temporary** label on the `django` service, then redeploy:

   ```yaml
       labels:
         caddy: ${CADDY_HOSTNAME:-}
         caddy.reverse_proxy: "{{upstreams 9000}}"
         caddy.import: ratelimit
         caddy.tls: internal        # TEMP — do NOT commit; prod needs real public certs
   ```

   `just mini` again to apply (caddy-docker-proxy reconfigures when django is
   recreated), and `git checkout docker-compose.yaml` when you're done. Confirm
   TLS now completes:
   `curl -svk https://erics-mac-mini.tail571dc2.ts.net/player/1/ 2>&1 | tail -5`
   → should reach a `302`, not an `internal error`.

3. Aim the script at **Caddy, not `:9000`** (hitting Daphne directly bypasses
   the edge and shows zero limiting — a misleading "pass"), with `--insecure`
   for the internal-CA cert:

   ```bash
   python3 project/app/manually_test_rate_limiting.py \
       --base-url https://erics-mac-mini.tail571dc2.ts.net --insecure \
       --concurrency 20 --duration 30
   ```

4. **Pass criterion:** `ok/s` (accepted 2xx/3xx) plateaus at the configured rate
   — ~5/s for `events 50 / window 10s`, after an initial burst of ~50 — while
   `429/s` carries the rest and `err` stays 0 (Caddy sheds cleanly: no 5xx, no
   timeouts). A passing run looks like:

   ```
    elapsed   req/s   ok/s  429/s    done   err    p95   canary
         1s      77     45     32      77     0   486m   [302]   <- ~50-event burst allowance
         2s     177      0    177     254     0   166m   [429]
        30s     200      3    197    5067     0   185m   [429]
   -------------------------------------------------------------
   Total: 5067   accepted (2xx/3xx): ~200 (~7/s)   rate-limited (429): ~4865   errored: 0
   ```

   In the mini's Grafana, Postgres backends (`sum(pg_stat_database_numbackends)`)
   should stay flat — the flood never reaches the app.

Caveat: the limit keys on client IP, so running from one machine means the
`canary` shares the bucket and flips to `[429]` too (correct behavior). To see
the "other users unaffected" property, hit the app from a second IP (e.g. your
phone on cellular) while the flood runs.
