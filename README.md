# Bridge Server

An online [Duplicate Bridge](https://en.wikipedia.org/wiki/Duplicate_bridge) game
server built with Django 6.0. It supports both human players (via a web UI) and
AI bots (via a REST API), with real-time game updates delivered through
Server-Sent Events (SSE).

## Features

- **Play Bridge in your browser** — full auction and play, with Bridge
  visibility rules enforced (you see your own cards; partner's cards and the
  dummy appear only when the rules allow).
- **Bots welcome** — synthetic players authenticate over a REST API and play
  alongside (or against) humans. See [`docs/README.api.md`](docs/README.api.md).
- **Real-time updates** — a write to the database fires a Postgres trigger, a
  listener process turns that into an event, and django-eventstream publishes it
  over Redis to every connected client. Nobody polls, and no code path has to
  remember to broadcast.
- **Duplicate tournaments** — movement-based duplicate mechanics with
  matchpoint scoring.
- **Google sign-in** — optional OAuth login via django-allauth.

## Technology Stack

- **Framework**: Django 6.0 on the Daphne ASGI server (async)
- **Database**: PostgreSQL 17, which doubles as the change-notification bus
  (LISTEN/NOTIFY)
- **Cache / PubSub**: Redis (django-eventstream's pub/sub transport)
- **Real-time**: Server-Sent Events via django-eventstream
- **Reverse proxy**: Caddy, in production only (TLS and rate limiting)
- **Package manager**: [uv](https://docs.astral.sh/uv/)
- **Task runner**: [Just](https://just.systems/)
- **Python**: 3.12 or newer

Game rules (card validation, legal bids, contract parsing, seat management) come
from a separate `bridge` library; the Django app handles persistence, players,
and the web/API layers.

## Quick Start

You'll need `git`, [`just`](https://just.systems/),
[`uv`](https://docs.astral.sh/uv/), `jq`, and Docker. Platform-specific
prerequisite instructions (Ubuntu, Debian, macOS) are in
[`README.developer.md`](README.developer.md).

```bash
# Install dependencies (creates a project-local .venv automatically)
just uv-install

# Generate the secret the app needs
just ensure-django-secret    # Django SECRET_KEY

# Set up the database, then run the dev server on http://localhost:9000
just migrate
just runme
```

`just runme` runs the web server natively (no Docker); it runs the fast tests
first, generates missing secrets, runs migrations, creates a superuser if needed,
and enables auto-reload. It still needs Docker for PostgreSQL, Redis, and the
change-notifier, which it starts for you.

To bring up the whole stack (Django, PostgreSQL, Redis, the bot, the tournament
clock and the notifier) via Docker Compose:

```bash
just dev
```

`just dev-monitoring` adds Grafana and Prometheus locally.

Run `just --list` to see all available commands.

## Testing

```bash
just ft                 # Fast parallel tests — preferred during development
just test               # Full suite, under coverage
just cover              # `just test`, then write and open htmlcov/index.html
just k <pattern>        # Run a specific test by name
just mypy               # Type checking
just ui-test-headless   # Playwright UI tests (headless)
```

## Documentation

- [`CLAUDE.md`](CLAUDE.md) — architecture deep-dive (models, channels, views,
  middleware) and full command reference
- [`README.developer.md`](README.developer.md) — prerequisites per OS and how to
  run locally vs. deploy
- [`docs/README.api.md`](docs/README.api.md) — REST API for bots
- [`docs/README.sse.md`](docs/README.sse.md) — how updates reach the browser: one
  connection per page, one named event per kind of update
- [`docs/README.listen-notify.md`](docs/README.listen-notify.md) — how a database
  write turns into an event, without anyone remembering to broadcast
- [`docs/README.rapid-readers.md`](docs/README.rapid-readers.md) — why query logic
  lives in `app/readers.py`
- [`docs/README.google-oauth.md`](docs/README.google-oauth.md) /
  [`docs/SETUP.google-oauth.md`](docs/SETUP.google-oauth.md) /
  [`docs/DEPLOY.google-oauth.md`](docs/DEPLOY.google-oauth.md) — Google sign-in
- [`docs/README.hosting.md`](docs/README.hosting.md) /
  [`docs/README.ubuntu-hetz.setup.md`](docs/README.ubuntu-hetz.setup.md) —
  hosting and deployment
- [`docs/README.monitoring.md`](docs/README.monitoring.md) — Prometheus, Grafana,
  Sentry, profiling
- [`docs/perf/`](docs/perf/) — the two 2026 outages, what actually caused them,
  and the rate limits that now shed that load at the edge
- [`docs/README.related.md`](docs/README.related.md) — other online Bridge
  services

## Deployment

```bash
just prod               # Deploy to production (requires the hetz-bridge Docker context)
just beta               # Deploy to beta.bridge.offby1.info
```

See [`docs/README.hosting.md`](docs/README.hosting.md) and
[`docs/README.ubuntu-hetz.setup.md`](docs/README.ubuntu-hetz.setup.md) for the
full procedure.

## License

Licensed under the GNU Affero General Public License v3.0. See
[`COPYING`](COPYING) for the full text.
