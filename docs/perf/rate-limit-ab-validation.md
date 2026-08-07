# A/B validating the Caddy rate-limit fix on a beta box

Goal: prove the rate-limit branch actually fixes the 2026-07-15 blackout, by an
A/B where the **only** variable is the branch:

1. Install **main** (the vulnerable version) on a beta box → **reproduce the blackout**.
2. Switch the beta box to **this branch** (the fix).
3. Run the **identical** stress client → observe **no blackout**.

See `crawler-repro.md` for the mechanism and `sse-connections.md` for the
red-herring that SSE was not involved.

## What makes the A/B valid (read this first)

These are the traps we hit while flailing on the mini. Get them right or the
result is meaningless.

1. **Both runs must go through the real Caddy front door** (`https://host/… →
   Caddy → Daphne`). The fix lives *inside Caddy*. If the client hits Daphne
   directly (`:9000`) or via a `tailscale serve → :9000` bypass, it skips Caddy
   on *both* branches — you'd get a blackout both times and wrongly conclude the
   fix doesn't work.
2. **Run the stress client close to the box** — on it, or in the same
   datacenter. A single laptop over tailscale/the internet can't offer enough
   real concurrency (CPython + a TLS handshake per request + network latency);
   the load gets throttled *before* Daphne and you won't reproduce the blackout
   even on main. (This is exactly why the mini looked "fine" at `--concurrency
   200`: `backends` stayed at 8.)
3. **Use open-loop load (`--rate`), not closed-loop (`--concurrency`).**
   Closed-loop caps in-flight requests and settles into slow-but-alive
   equilibrium. The blackout was an *unbounded* pileup → wedge. Only a fixed
   arrival rate above capacity drives it over the edge.
4. **Use prod-class hardware.** A 10-core M4 absorbs far more than the Hetzner
   VPS prod runs on — you may not be able to black it out at all. Use `just
   beta` (Hetzner + real domain + real Let's Encrypt cert; no `tls internal`
   gymnastics), which mirrors prod.

Scope note: the limit is **per source IP**, so a single stress client validates
the single-source case — which is what actually hit prod (`93.123.109.102`, one
IP). A distributed flood is a separate concern (a global cap / WAF), not this.

## Procedure

### 0. Prep the beta box

- Deploy with `just beta` (hostname `beta.bridge.offby1.info`, Hetzner context).
- Load a **prod-like dataset** (the outage needed real query cost — an empty DB
  won't saturate). A prod dump is ideal (~35 tournaments / ~228 players).
- Pick a load box **near** beta (the beta box itself, or another Hetzner box).
  Install a stress client there — either this repo's tester (`python3`, stdlib)
  or `vegeta`.

### 1. Reproduce the blackout on `main`

```bash
git checkout main && just beta
```

⚠️ **main's `_deploy` does not start Caddy** — that fix is on this branch (the
`[merge to main]` commit). So bring Caddy up by hand for the main run, or the
flood has no front door:

```bash
CADDY_HOSTNAME=beta.bridge.offby1.info DOCKER_CONTEXT=hetz-bridge-beta \
  COMPOSE_PROFILES=beta,monitoring docker compose up -d caddy
```

Then flood the **real front door**, open-loop, from the nearby box. Start below
capacity and ratchet `--rate` up until it wedges:

```bash
python3 project/app/manually_test_rate_limiting.py \
  --base-url https://beta.bridge.offby1.info \
  --rate 200 --duration 90
# ...raise --rate (400, 800, …) until you see the wedge.
```

Watch Grafana `sum(pg_stat_database_numbackends)` (or psql) on beta. **Blackout
confirmed** when: `backends` climbs toward the 200 cap, `err`/`0=` (timeouts)
rise, the `canary` stops responding, and the site is unreachable in a browser.
Record the `--rate` that did it.

### 2. Switch to the fix and re-run identically

```bash
git checkout <this-branch> && just beta   # now starts Caddy itself, with the rate limit
```

Run the **exact same command** (same `--rate`, `--duration`):

```bash
python3 project/app/manually_test_rate_limiting.py \
  --base-url https://beta.bridge.offby1.info \
  --rate 200 --duration 90
```

### 3. Success criteria

| Signal | main (broken) | this branch (fixed) |
|---|---|---|
| `429/s` | ~0 | carries most of the load |
| `ok/s` (accepted) | climbs then collapses | plateaus at ~5/s |
| `err` / `0=` (timeouts) | rises → blackout | stays 0 |
| `sum(pg_stat_database_numbackends)` | → ~200 (cap) | flat near baseline |
| canary / browser during flood | unresponsive | fast |

The fix is validated when the same flood that blacked out `main` comes back
almost entirely `429` on this branch, Daphne's backends stay flat, and a normal
request stays fast — i.e. the load is shed at the edge and never reaches Daphne.

## Notes / gotchas

- **`--header 'X-Forwarded-Proto: https'` is for the *direct-to-Daphne* disease
  repro only** (bypassing Caddy on `:9000`, where `SECURE_SSL_REDIRECT` would
  otherwise 301 every request). Do **not** use it for the A/B — the A/B goes
  through Caddy over real HTTPS.
- If `manually_test_rate_limiting.py` reports **client-saturated** dispatches,
  the *client* (not beta) is the bottleneck: raise `--max-inflight`, use a
  closer/beefier load box, or switch to `vegeta -rate=`.
- `vegeta` is a fine substitute for the flood and also reports per-code counts:
  `echo 'GET https://beta.bridge.offby1.info/players/?tournament__display_number=1'
  | vegeta attack -rate=200/s -duration=90s | vegeta report`.
