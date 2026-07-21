#!/usr/bin/env python3
"""Reproduce the crawler that took prod down, so you can watch it happen locally.

Background
----------
On 2026-07-15 a crawler (93.123.109.102) spent ~90s walking the sortable /
filterable list views -- /players/, /hand/, /board/ -- following every
combination of tournament filter x sort column x page number. Each URL is a
distinct, uncached, prefetch+count query. Fired concurrently they saturated
Daphne's sync-view thread pool (the asgiref thread executor that runs our sync
Django views), and latency climbed monotonically: 63ms -> 3600ms. The tell in
the logs was that even a trivial `GET /player/N/ => 302` redirect -- which does
essentially no DB work -- was taking 3+ seconds. That's worker/connection-pool
exhaustion, not slow SQL. (SSE connections played no part: the crawler never
requested any /events/ URL, so it created none.)

What this script does
---------------------
Closed-loop load generator: --concurrency worker threads each issue list-view
requests back-to-back, mirroring the crawler's URL fan-out. Meanwhile a single
low-rate "canary" thread measures a cheap endpoint (a /player/N/ redirect by
default) so you can watch an innocent request degrade while the flood runs --
the same signature you saw in prod. Raise --concurrency until latency climbs.

It doubles as a manual rate-limit test: aimed at Caddy (which fronts the app in
the Docker stack), the per-status / 429-per-second output shows the edge
shedding excess load before it reaches Daphne (see the summary printed at exit).

Standalone: Python 3 stdlib only, no dependencies, no venv needed. Not a pytest
test (the name deliberately doesn't match `test_*.py`); run it by hand.

Examples
--------
    # Run from the repo root. Start the app first (native dev server on :9000):
    #   just runme
    python3 project/app/manually_test_rate_limiting.py
    python3 project/app/manually_test_rate_limiting.py --concurrency 60 --duration 60

    # To exercise Caddy's per-IP rate limit, aim at Caddy -- NOT :9000, which
    # bypasses it (run the Docker stack, e.g. `just dcu`):
    python3 project/app/manually_test_rate_limiting.py --base-url https://localhost --insecure

Point it at your own local instance. Do NOT aim it at prod.
"""

from __future__ import annotations

import argparse
import itertools
import random
import ssl
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import Counter, deque

# The query-param space the real crawler walked. Adjust the ranges to match
# whatever data your local DB actually has (see --tournaments / --pages).
SORT_COLUMNS = ["", "who", "partner", "where", "tournament", "last_activity"]


def build_url_space(base_url: str, tournaments: range, pages: range) -> list[str]:
    """Every list-view URL the crawler would follow -- the combinatorial trap."""
    base = base_url.rstrip("/")
    urls: list[str] = []

    # /players/ : tournament filter x sort column x page  (the worst offender)
    for t, sort, page in itertools.product(tournaments, SORT_COLUMNS, pages):
        q = [f"tournament__display_number={t}"]
        if sort:
            q.append(f"sort={sort}")
        if page > 1:
            q.append(f"page={page}")
        urls.append(f"{base}/players/?" + "&".join(q))

    # bare /players/ sorts and pages (no tournament filter)
    for sort in SORT_COLUMNS:
        urls.append(f"{base}/players/?sort={sort}" if sort else f"{base}/players/")
    for page in pages:
        urls.append(f"{base}/players/?page={page}")

    # /hand/ and /board/ filtered by tournament
    for t in tournaments:
        urls.append(f"{base}/hand/?board__tournament__display_number={t}")
        urls.append(f"{base}/board/?tournament__display_number={t}")

    return urls


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Don't follow 3xx -- we want to time the app's own response, not chase it
    to /accounts/login/. A redirect surfaces as HTTPError, which we count as a
    perfectly good (and cheap) response."""

    def redirect_request(self, *args, **kwargs):  # noqa: ANN002, ANN003
        return None


def make_opener(insecure: bool) -> urllib.request.OpenerDirector:
    handlers: list[urllib.request.BaseHandler] = [_NoRedirect()]
    if insecure:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        handlers.append(urllib.request.HTTPSHandler(context=ctx))
    return urllib.request.build_opener(*handlers)


def fetch(
    opener: urllib.request.OpenerDirector,
    url: str,
    timeout: float,
    headers: dict[str, str],
) -> tuple[int, float]:
    """Return (status_code, elapsed_seconds). status 0 means the request errored
    out (timeout / connection refused) -- which is itself the symptom once the
    server stops answering."""
    start = time.monotonic()
    req = urllib.request.Request(url, headers=headers)
    try:
        with opener.open(req, timeout=timeout) as resp:
            resp.read()
            return resp.status, time.monotonic() - start
    except urllib.error.HTTPError as e:
        # 302/404/500 etc. -- a real response; drain and count it.
        try:
            e.read()
        except Exception:
            pass
        return e.code, time.monotonic() - start
    except Exception:
        return 0, time.monotonic() - start


class Stats:
    """Thread-safe latency collector with a rolling window for per-second output."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.window: deque[tuple[float, int]] = deque()  # (latency, status) since last report
        self.total = 0
        self.errors = 0
        self.status: Counter[int] = Counter()  # cumulative count per HTTP status (0 = errored out)
        self.client_saturated = 0  # open-loop: dispatches skipped because in-flight cap was hit
        self.canary: deque[tuple[float, float, int]] = deque(
            maxlen=20
        )  # (wallclock, latency, status)

    def record(self, latency: float, status: int) -> None:
        with self.lock:
            self.window.append((latency, status))
            self.total += 1
            self.status[status] += 1
            if status == 0 or status >= 500:
                self.errors += 1

    def record_canary(self, latency: float, status: int) -> None:
        with self.lock:
            self.canary.append((time.monotonic(), latency, status))

    def note_saturated(self) -> None:
        with self.lock:
            self.client_saturated += 1

    def snapshot_window(self) -> list[tuple[float, int]]:
        with self.lock:
            w = list(self.window)
            self.window.clear()
            return w

    def latest_canary(self) -> tuple[float, int] | None:
        with self.lock:
            if not self.canary:
                return None
            _, latency, status = self.canary[-1]
            return latency, status


def pct(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return 0.0
    idx = min(len(sorted_vals) - 1, int(round((p / 100.0) * (len(sorted_vals) - 1))))
    return sorted_vals[idx]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reproduce the list-view crawler load locally.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--base-url", default="http://localhost:9000")
    parser.add_argument(
        "--concurrency", type=int, default=20, help="number of worker threads hammering list views"
    )
    parser.add_argument(
        "--duration", type=float, default=0.0, help="seconds to run (0 = until Ctrl-C)"
    )
    parser.add_argument(
        "--timeout", type=float, default=30.0, help="per-request timeout in seconds"
    )
    parser.add_argument(
        "--tournaments", default="1-44", help="tournament display-number range, e.g. 1-44"
    )
    parser.add_argument("--pages", default="1-10", help="page range, e.g. 1-10")
    parser.add_argument(
        "--canary-path",
        default="/player/1/",
        help="cheap endpoint to probe (a 302 redirect does ~no DB work)",
    )
    parser.add_argument(
        "--canary-interval", type=float, default=2.0, help="seconds between canary probes"
    )
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="skip TLS verification (for https local/self-signed)",
    )
    parser.add_argument(
        "--rate",
        type=float,
        default=0.0,
        help="open-loop: dispatch this many requests/sec regardless of completion "
        "(0 = closed-loop, use --concurrency). Needed to reproduce the unbounded "
        "pileup/wedge -- closed-loop only reaches a slow equilibrium.",
    )
    parser.add_argument(
        "--max-inflight",
        type=int,
        default=2000,
        help="open-loop only: cap on simultaneous in-flight requests (protects the "
        "client); hitting it is reported as client-saturated.",
    )
    parser.add_argument(
        "--header",
        action="append",
        default=[],
        metavar="'K: V'",
        help="extra request header, repeatable (e.g. --header 'X-Forwarded-Proto: https' "
        "to hit Daphne directly without SECURE_SSL_REDIRECT 301ing you).",
    )
    args = parser.parse_args()

    def parse_range(s: str) -> range:
        lo, _, hi = s.partition("-")
        return range(int(lo), int(hi) + 1) if hi else range(int(lo), int(lo) + 1)

    headers: dict[str, str] = {}
    for h in args.header:
        key, _, value = h.partition(":")
        headers[key.strip()] = value.strip()

    urls = build_url_space(args.base_url, parse_range(args.tournaments), parse_range(args.pages))
    canary_url = args.base_url.rstrip("/") + args.canary_path

    print(f"Target        : {args.base_url}")
    print(f"URL space     : {len(urls)} distinct list-view URLs")
    if args.rate:
        print(f"Mode          : open-loop {args.rate:g} req/s (max in-flight {args.max_inflight})")
    else:
        print(f"Mode          : closed-loop, {args.concurrency} worker threads")
    if headers:
        print(f"Headers       : {headers}")
    print(f"Canary        : {canary_url} every {args.canary_interval}s")
    print(f"Duration      : {'until Ctrl-C' if args.duration == 0 else f'{args.duration}s'}")
    print("-" * 78)
    if args.rate:
        print("Open-loop: fires at a fixed rate regardless of completion -- this is what")
        print("reproduces the unbounded pileup/wedge. Raise --rate past capacity.\n")
    else:
        print("Closed-loop reaches a slow-but-alive equilibrium; use --rate for the wedge.\n")

    stats = Stats()
    stop = threading.Event()
    opener = make_opener(args.insecure)

    def do_request() -> None:
        status, latency = fetch(opener, random.choice(urls), args.timeout, headers)
        stats.record(latency, status)

    def closed_loop_worker() -> None:
        while not stop.is_set():
            do_request()

    def open_loop_dispatcher() -> None:
        # Fire at a fixed rate regardless of completion, each request in its own
        # daemon thread, so slow responses let in-flight requests pile up without
        # bound -- the arrival pattern a real crawler has, and the one a closed
        # loop can't produce. A semaphore caps concurrent in-flight to protect the
        # client; overflow is counted (client, not server, was the limit).
        inflight = threading.BoundedSemaphore(args.max_inflight)
        interval = 1.0 / args.rate

        def run_one() -> None:
            try:
                do_request()
            finally:
                inflight.release()

        next_t = time.monotonic()
        while not stop.is_set():
            if inflight.acquire(blocking=False):
                threading.Thread(target=run_one, daemon=True).start()
            else:
                stats.note_saturated()
            next_t += interval
            delay = next_t - time.monotonic()
            if delay > 0:
                stop.wait(delay)

    def canary() -> None:
        probe = make_opener(args.insecure)
        while not stop.is_set():
            status, latency = fetch(probe, canary_url, args.timeout, headers)
            stats.record_canary(latency, status)
            stop.wait(args.canary_interval)

    if args.rate:
        threads = [threading.Thread(target=open_loop_dispatcher, daemon=True)]
    else:
        threads = [
            threading.Thread(target=closed_loop_worker, daemon=True)
            for _ in range(args.concurrency)
        ]
    threads.append(threading.Thread(target=canary, daemon=True))
    started = time.monotonic()
    for t in threads:
        t.start()

    # ok/s = accepted (2xx/3xx) per second; 429/s = rate-limited per second.
    print(
        f"{'elapsed':>8} {'req/s':>7} {'ok/s':>6} {'429/s':>6} {'done':>7} {'err':>5} "
        f"{'p50':>6} {'p95':>6} {'max':>8}   canary"
    )
    try:
        while not stop.is_set():
            time.sleep(1.0)
            elapsed = time.monotonic() - started
            window = stats.snapshot_window()
            lats = sorted(latency * 1000 for latency, _ in window)  # ms
            rps = len(window)
            n_ok = sum(1 for _, status in window if 200 <= status < 400)  # accepted this second
            n429 = sum(1 for _, status in window if status == 429)  # rate-limited this second
            c = stats.latest_canary()
            if c is None:
                canary_str = "  (none yet)"
            else:
                c_secs, c_status = c
                c_ms = c_secs * 1000
                flag = " !!" if c_ms > 1000 else ""
                canary_str = f"{c_ms:8.0f}ms [{c_status}]{flag}"
            print(
                f"{elapsed:7.0f}s {rps:7d} {n_ok:6d} {n429:6d} {stats.total:7d} {stats.errors:5d} "
                f"{pct(lats, 50):5.0f}m {pct(lats, 95):5.0f}m {pct(lats, 100):7.0f}m"
                f"   {canary_str}"
            )
            if args.duration and elapsed >= args.duration:
                break
    except KeyboardInterrupt:
        print("\nInterrupted.")
    finally:
        stop.set()

    print("-" * 78)
    by_status = ", ".join(f"{code}={n}" for code, n in sorted(stats.status.items())) or "(none)"
    accepted = sum(n for code, n in stats.status.items() if 200 <= code < 400)
    limited = stats.status.get(429, 0)
    elapsed_s = max(1e-9, time.monotonic() - started)
    print(
        f"Total: {stats.total}   accepted (2xx/3xx): {accepted} "
        f"(~{accepted / elapsed_s:.1f}/s)   rate-limited (429): {limited}   "
        f"errored/timed out: {stats.errors}"
    )
    print(f"By status: {by_status}   (0 = errored out / timed out)")
    if args.rate and stats.client_saturated:
        print(
            f"Client-saturated: {stats.client_saturated} dispatches skipped (in-flight hit "
            f"--max-inflight={args.max_inflight}). The client, not the server, was the "
            f"limit here -- raise --max-inflight or use a beefier/closer client."
        )
    print("Pool test: if the canary latency climbed or timed out, you reproduced the")
    print("pool-exhaustion that took prod down.")
    print("Rate-limit test (aim --base-url at Caddy, NOT :9000): a working per-IP limit")
    print("shows accepted (ok/s) plateauing at the configured rate while 429/s carries")
    print("the rest, and err staying 0.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
