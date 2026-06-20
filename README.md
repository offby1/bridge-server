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
- **Real-time updates** — game state flows through django-eventstream → Redis →
  SSE, so every client stays in sync without polling.
- **Duplicate tournaments** — movement-based duplicate mechanics with
  matchpoint scoring.
- **Google sign-in** — optional OAuth login via django-allauth.

## Technology Stack

- **Framework**: Django 6.0 on the Daphne ASGI server (async)
- **Database**: PostgreSQL 17
- **Cache / PubSub**: Redis (django-eventstream backend)
- **Real-time**: Server-Sent Events via django-eventstream
- **Package manager**: [uv](https://docs.astral.sh/uv/)
- **Task runner**: [Just](https://just.systems/)
- **Python**: 3.12–3.13

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

# Generate the secrets the app needs
just ensure-django-secret    # Django SECRET_KEY
just ensure-skeleton-key     # API skeleton key

# Set up the database, then run the dev server on http://localhost:9000
just migrate
just runme
```

`just runme` starts just the web server natively (no Docker); it generates
missing secrets, runs migrations, creates a superuser if needed, and enables
auto-reload.

To bring up the full stack (Django + PostgreSQL + Redis + bots + monitoring) via
Docker Compose:

```bash
just dcu
```

Run `just --list` to see all available commands.

## Testing

```bash
just ft                 # Fast parallel tests — preferred during development
just test               # Full suite with coverage report (htmlcov/index.html)
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
- [`docs/README.auth.md`](docs/README.auth.md) /
  [`docs/README.google-oauth.md`](docs/README.google-oauth.md) — authentication
- [`docs/README.hosting.md`](docs/README.hosting.md) /
  [`docs/README.ubuntu-hetz.setup.md`](docs/README.ubuntu-hetz.setup.md) —
  hosting and deployment
- [`docs/README.monitoring.md`](docs/README.monitoring.md) — Prometheus, Grafana,
  Sentry, profiling
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
