# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Conventions

- Always read CLAUDE.md and justfile before starting any task. Use `just` commands (e.g., `just k` for tests) instead of raw shell commands.
- Never write to personal memory files — all documentation goes in version-controlled project docs.

## Change Philosophy

- Prefer minimal, targeted fixes. Do NOT over-engineer solutions or make unnecessary changes across multiple files.
- Before proposing a fix, identify the minimum number of changes needed and confirm the approach before implementing.

## Testing

- Always run tests after making changes using the project's test runner (check justfile first).
- Write minimal reproducing tests before fixing bugs when possible.
- Do not write unnecessary test files or disable tests to make things pass.

## Safety & Production

- NEVER attempt to access production systems, Docker contexts, or databases unless explicitly asked.
- NEVER store passwords, keys, or secrets in plaintext or commit them to the repository.

## Approach

- When stuck after 2 failed attempts on the same problem, STOP and explain what you've tried and ask the user for direction instead of continuing to loop.
- Do not make claims about the user's setup (OS, services, accounts) without verifying first.

## Project Overview

This is an online Bridge card game server built with Django 6.0. It supports both human players (via web UI) and AI bots (via REST API), with real-time game updates delivered through Server-Sent Events (SSE).

## Essential Commands

All commands use [Just](https://just.systems/) command runner. See `justfile` for complete list.

### Development
```bash
just runme              # Start Django dev server on localhost:9000 (native, no Docker)
just dev                # Start the local Docker Compose stack (Django + Postgres + Redis + bot + clock + notifier)
just dev-monitoring     # Same as `just dev`, plus Grafana/Prometheus/pyroscope locally
just notifier           # Run the change-notifier natively instead of in Docker
just shell              # Django shell with pre-populated queries
just sp                 # Quick shell_plus (no dependencies)
```

`just dcu` is gone; it now prints "Use `just dev` now" and fails.

### Testing
```bash
just ft                 # Fast tests (parallel, 8 workers via pytest-xdist) - PREFERRED for development
just test               # Full test suite under coverage - slower
just cover              # `just test`, then build htmlcov/index.html and open it
just t                  # Tests with exitfirst and failed-first
just k <pattern>        # Run specific test by name (e.g., just k hand_events)
just mypy               # Type checking with dmypy daemon (also runs `ty`, whose result is ignored)

# UI Tests (Playwright)
just ui-test-headless   # Run UI tests headless (PREFERRED - won't interfere with laptop use)
just ui-test            # Run UI tests headed (visible browser - avoid during active work)
just ui-test-mobile     # Run UI tests with mobile viewport (headed)
```

**Important Testing Notes**:
- **Always use `just ft` for quick test verification during development** - it's much faster than `just test`
- **Check coverage after every important code change** - Run `just cover`, which runs the suite under coverage and then writes and opens `htmlcov/index.html`. (`just test` collects the coverage data but does not build the HTML report.)
- **Always use `just` commands, not `uv run` directly** - The justfile sets up required environment variables that `uv run` lacks. Direct `uv run` commands will often fail.
- Use `just test` when you are doing final verification before committing
- Always use `just ui-test-headless` for UI tests unless specifically debugging browser behavior visually. Headless mode allows laptop use during test runs without interference.
- Use `just k <pattern>` to run individual tests. NEVER use `pytest` directly or `uv run pytest`. The `just k` command is the standard way to run individual tests in this project.

### Database
```bash
just migrate            # Run migrations
just makemigrations     # Create new migrations
just dumpdata           # Export DB to fixture JSON
just load <fixture>     # Import fixture (drops DB first); alias for `just fixture`
just drop               # Drop the local Postgres and Redis volumes
just backup             # pg_dump the database, with secrets redacted
just graph              # Generate ER diagram (opens in browser)
```

The fixtures that exist live in `project/app/fixtures/`: `usual_setup`,
`fresh_tournament`, `nearly_completed_tournament`,
`completed-tournament-20-players`, `two_boards_one_of_which_is_played_almost_to_completion`,
`two_by_two_all_tied`, and `jd-souther-is-ready-to-play-a-heart`.

### Deployment
```bash
just prod               # Deploy to production (requires hetz-bridge Docker context, main branch, clean tree)
just beta               # Deploy to beta.bridge.offby1.info (hetz-bridge-beta context)
just mini               # Deploy to the mac mini over Tailscale
```

## Architecture

### Technology Stack

- **Framework**: Django 6.0 with Daphne ASGI server (async support)
- **Database**: PostgreSQL 17 (max_connections=200), which is also the change-notification
  bus, via LISTEN/NOTIFY
- **Cache/PubSub**: Redis (django-eventstream's pub/sub transport, and the Django cache)
- **Real-time**: Server-Sent Events (SSE) via django-eventstream
- **Reverse proxy**: Caddy, in production and beta only — TLS plus rate limiting
- **Package Manager**: uv (not pip/poetry)
- **Python**: 3.12 or newer

### Settings Structure

Four settings modules, all in the `project` package (on disk: `project/project/`):

1. **`project/base_settings.py`** - Common settings
2. **`project/dev_settings.py`** - Development (DEBUG=True, browser reload)
3. **`project/prod_settings.py`** - Production and staging (Sentry, hardened security). It
   picks `DEPLOYMENT_ENVIRONMENT` itself: `"production"` when `COMPOSE_PROFILES` contains
   `prod`, otherwise `"staging"`.
4. **`project/test_settings.py`** - What the test suite runs under (`DEPLOYMENT_ENVIRONMENT = "test"`)

Set via `DJANGO_SETTINGS_MODULE` environment variable. The `justfile` exports this
automatically, defaulting to `project.dev_settings` and overriding it to
`project.test_settings` for every test recipe.

### Real-Time Event Architecture

**Critical Pattern**: a game state change reaches a client this way: something writes a
row; a Postgres trigger emits a NOTIFY on commit; the `notifier` process turns that into
a `send_event()` call; django-eventstream publishes it over Redis; whichever web process
holds the client's SSE connection writes it down the socket.

Two documents cover the two halves, and both are current:

- `docs/README.listen-notify.md` — **who fires the broadcast.** Triggers plus the
  `notifier` management command plus `app/broadcast.py`. Almost nothing calls `send_event`
  inline any more, and new code should not start: add a broadcaster instead.
- `docs/README.sse.md` — **how it reaches the browser.** One connection per page, one
  named event per kind of update.

There are exactly two SSE endpoints, and adding a third is almost certainly a mistake.
See `docs/README.sse.md` for why, and for the whole design.

- **`/events/all/`** — everything a browser needs, on one connection.
- **`/events/player/json/<player_pk>/`** — the programmatic interface for clients
  somebody else writes. See `docs/README.api.md`.

#### Channel Manager (`app/channelmanager.py`)

`MyChannelManager` does two jobs. `get_channels_for_request()` decides which channels
`/events/all/` carries for the viewer asking, and `can_read_channel()` decides who may
read a given channel. The latter **denies anything it doesn't recognise**, so a new
channel needs a rule there or it will silently deliver nothing.

Channel names live in `app/sse_channels.py`, except the chat one, which is
`players:<pk>_<pk>` and belongs to `Message.channel_name_from_player_pks`.

#### How to send events

Every kind of update has its own event name, collected in `SSEEventTypes`
(`app/sse_events.py`). Don't send `"message"`: the browser's channels share one
connection, so the name is how a listener knows what it just received.

Broadcasts live in `app/broadcast.py`, and the `notifier` calls them when a trigger fires;
they use the shared `send_timestamped_event` helper in `app/models/hand.py` rather than
calling `send_event` themselves. A broadcaster looks like this:

```python
from app.models.hand import send_timestamped_event
from app.sse_channels import SSEChannels
from app.sse_events import SSEEventTypes, create_table_event

send_timestamped_event(
    channel=SSEChannels.table_html(hand.pk),
    event_type=SSEEventTypes.TABLE,
    data=create_table_event(trick_counts_string='{"N/S": 3, "E/W": 2}'),
)
```

The event name is a contract between Python and JavaScript that no type checker sees.
`app/test_sse_event_types.py` checks that the browser subscribes to the names we send.

### Game Logic Organization

#### Core Models (`app/models/`)

**`hand.py`** (~1000 lines) - Most complex model. Holds `Hand` plus the `Call` and
`Play` models.
- Four foreign keys, `North`/`East`/`South`/`West`, name who sits where; the cards
  themselves come from the `Board` the hand is played from
- Auction and play history are rows: one `Call` row per call, one `Play` row per card,
  both append-only. There is no JSONField.
- `Hand.get_xscript()` builds (and caches) a `bridge.xscript.HandTranscript` from those
  rows; nearly every derived question — whose turn, what the contract is, who won which
  trick — is answered from the transcript rather than stored
- Key write methods: `add_call()`, `add_play_from_model_player()`,
  `do_end_of_hand_stuff()`. `is_complete` is a redundant field, recomputed by
  `_update_redundant_fields()`.
- Read-only query logic that used to live here is now in `app/readers.py` — see
  `docs/README.rapid-readers.md`

**`player.py`** (~630 lines)
- Links User to Player (one-to-one), and tracks the player's current hand
- Partnership management (`partner_with`, `break_partnership`)
- Bot flags: `synthetic` (this player *is* a bot) and `allow_bot_to_play_for_me` (a human
  who has handed control over). `effective_allow_bot_to_play_for_me` also covers dummy,
  whose cards declarer plays.

**`tournament.py`**
- Movement-based duplicate bridge mechanics
- Signup deadline enforcement
- Matchpoint scoring calculations

**`board.py`**
- Pre-defined card deals
- Dealer and vulnerability assignments

#### Bridge Library Integration
The project imports a separate `bridge` library (from GitLab) for:
- Card representation and validation
- Auction rule enforcement (valid bids, legal doubles/redoubles)
- Contract parsing (e.g., "3NT", "4♠X")
- Seat/direction management (North/South/East/West)
- Hand transcript generation (xscript format for bots)

**Important**: The `bridge` library handles game rules; Django models handle game state persistence and player management.

#### Readers (`app/readers.py`)

Query logic — anything that computes something for a caller to look at, with no side
effects — lives in `app/readers.py` as plain functions taking model instances. **The
dependency points one way: readers import from models, models never import from readers.**
Views, the bot API, management commands, `app/broadcast.py` and tests all call readers
directly, as `import app.readers` then `app.readers.get_whatever(...)`.

A read that a *template* used to make should become a value the view computes and passes
in the context, not a delegating method left on the model — otherwise the template still
triggers queries at render time. `docs/README.rapid-readers.md` has the full story and the
traps.

### View Patterns

#### Hand Visibility Rules (`app/readers.py`)

`app.readers.get_display_skeleton()` implements Bridge visibility rules:

- **Your cards**: Always visible
- **Partner's cards**: Visible only after dummy is exposed (contract determined + opening lead made)
- **Opponents' cards**: Never visible (except cards already played)
- **Open access mode** (`hand.open_access=True`): Override all rules, show everything (for development/spectating)

#### Two Rendering Modes
1. **Interactive mode** - Active player sees bidding box or card selection
2. **Read-only mode** - Spectators and players waiting for their turn

#### Template Context
Templates receive:
- `card_display` - Skeleton showing which cards are visible
- `active_seat` - Whose turn it is (gets `.active` CSS class)
- `viewers_seat` - Which player is viewing (determines perspective)

### API for Bots (`/three-way-login/` endpoint)

Bots authenticate once via HTTP Basic Auth, then use session cookies for subsequent requests.

**Authentication Flow**:
```bash
# 1. Login and get session cookie
curl -c cookies.txt -u 'username:password' http://localhost:9000/three-way-login/

# 2. Get hand transcript
curl -b cookies.txt http://localhost:9000/serialized/hand/123/

# 3. Subscribe to events (long-lived SSE connection)
curl -b cookies.txt http://localhost:9000/events/player/json/1/

# 4. Make a call.  No hand pk in the URL: the server applies the call to whichever
#    hand you are currently seated at.
curl -b cookies.txt -X POST \
  -H "X-CSRFToken: <from-cookie>" \
  -d "call=1%E2%99%A3" \
  http://localhost:9000/call/

# 5. Play a card.  Likewise no hand pk.
curl -b cookies.txt -X POST \
  -H "X-CSRFToken: <from-cookie>" \
  -d "card=%E2%99%A52" \
  http://localhost:9000/play/
```

**CSRF Protection**: POST requests require either:
- `X-CSRFToken` header with csrftoken cookie value, OR
- `csrfmiddlewaretoken` form field

See `docs/README.api.md` for complete API documentation.

### Middleware Stack

Our own middleware, all in `app/middleware/`:

- **SwallowAnnoyingExceptionMiddleware** - Turns `asyncio.CancelledError` (a client that
  hung up mid-response) into a warning instead of a 30-line traceback
- **NoIndexMiddleware** - Adds `X-Robots-Tag`
- **AddRequestIdToSQLConnectionMiddleware** - Sets Postgres `application_name` to the
  request id, so a query in the database log can be traced back to its request
- **AddVersionHeaderMiddleware** - Includes git commit in `X-Bridge-Version` header
- **RequestLoggingMiddleware** (`simple_access_log.py`) - One line per request. Its `ms=`
  figure starts at its own place in the chain, so it excludes everything listed above it.
- **SSEStreamLoggingMiddleware** - Logs each SSE stream's open and close, with a reason, a
  duration, and how many are open. Start here when something isn't updating.
- **BetterTimezoneMiddleware** - A wrapper around `tz_detect`

Third-party middleware also in the stack: CORS, HTTP compression,
`django_prometheus`'s before/after pair, `log_request_id` (which supplies the
`X-Request-Id` response header), WhiteNoise, debug toolbar, and allauth's
`AccountMiddleware`.

All middleware is registered in order in `base_settings.py`; the order matters.

## Development Workflow

### First-Time Setup

```bash
# Install dependencies (creates .venv automatically)
just uv-install

# Generate Django secrets
just ensure-django-secret    # Creates Django SECRET_KEY
just ensure-skeleton-key     # Creates API skeleton key

# Setup database
just migrate
just fixture usual_setup    # Optional: load a sample tournament and players
```

(`just ensure-django-secret` and `just ensure-skeleton-key` are marked private, so they
don't appear in `just --list`, but you can still run them by name. Every recipe that needs
them depends on them anyway, so `just runme` alone is usually enough.)

### Running Locally

**Native (no Docker)**:
```bash
just runme                  # Starts on localhost:9000
```
This automatically:
- Runs the fast test suite first (`just runme` depends on `just ft`)
- Generates secrets if missing
- Runs migrations
- Creates superuser if needed
- Starts PostgreSQL and Redis in Docker, plus the `notifier` container — so live updates
  flow even though Django itself is running natively
- Starts dev server with auto-reload

**Docker Compose Stack**:
```bash
just dev
```
Brings up Django, PostgreSQL, Redis, the bot, the tournament clock, and the notifier. It
conflicts with `just runme`, since both listen on port 9000.

Monitoring (Grafana, Prometheus, postgres-exporter, pyroscope) is gated behind the
`monitoring` compose profile, which `just dev` does *not* enable; use `just
dev-monitoring` for that. `just prod` and `just beta` enable it, along with the Caddy
reverse proxy.

### Testing Patterns

Tests use pytest with Django fixtures.

**Run specific test**:
```bash
just k test_hand_distribution    # By function name
just k "test_hand and auction"   # Pattern matching
```

**Parallel testing**: `just ft` uses 8 workers via pytest-xdist. Disable with `-n 0` for debugging.

**Coverage**: `just cover` runs the suite and then writes and opens `htmlcov/index.html`.
`just test` records the coverage data but stops short of the HTML.

Note that coverage says nothing about templates: `just test` warns that the Django
template coverage plugin disabled itself, because template debugging is off in the test
settings.

### Code Quality Checks

**CRITICAL**: Always run `just mypy` before committing code. Type checking must pass.

Pre-commit hooks will run automatically on `git commit`:
- Trailing whitespace removal
- Django-upgrade (auto-updates Django API usage)
- Ruff linting and formatting
- djLint (Django template linting)
- Justfile formatting

If hooks fail, they may auto-fix issues. Review changes and re-commit.

### Database Migrations

**Creating migrations**: Django automatically detects model changes.
```bash
just makemigrations
just migrate
```

**Resetting database**:
```bash
just drop                    # Docker only; refuses to run against a remote context
just migrate                 # Recreate schema
just fixture usual_setup     # Reload sample data (this also drops and migrates)
```

### Performance Testing

```bash
just stress --tiny --tempo-seconds=1.0   # Small stress test
just stress --tempo-seconds=0            # Maximum speed (no delays)
```

`just stress` runs `big_bot_stress` inside the `django` container, so it needs the Docker
stack up (`just dev`). Bots automatically join games and play hands. Capture the logs with
`just dump` (django) or `just dump-bot` (the bot), each of which writes a timestamped file.

For load-testing rather than gameplay, `project/app/manually_test_rate_limiting.py` floods
the list views; see `docs/perf/crawler-repro.md`.

## Important Configuration

### Environment Variables

Set by `justfile` or Docker Compose:

- **`DJANGO_SETTINGS_MODULE`** - Which settings module (dev_settings / prod_settings / test_settings)
- **`DJANGO_SECRET_FILE`** - Path to SECRET_KEY file
- **`DJANGO_SKELETON_KEY_FILE`** - Path to API skeleton key
- **`GOOGLE_OAUTH_CLIENT_ID_FILE`**, **`GOOGLE_OAUTH_CLIENT_SECRET_FILE`** - Paths to the
  OAuth credentials. Absent, the app runs fine without Google sign-in.
- **`PGHOST`**, **`PGUSER`**, **`PGPASS`** - PostgreSQL connection
- **`REDIS_HOST`** - Redis server (default: localhost)
- **`COMPOSE_PROFILES`** - Which compose profiles are active; `prod_settings` reads it to
  decide whether `DEPLOYMENT_ENVIRONMENT` is "production" or "staging"
- **`DOCKER_CONTEXT`** - Which Docker host to deploy to; defaults to `orbstack` on macOS
- **`PYINSTRUMENT`** - Set to `t` to enable the pyinstrument profiler; see `docs/perf/README.perf.md`

`DEPLOYMENT_ENVIRONMENT` is a *setting*, not an environment variable the justfile sets: the
settings modules compute it, and it takes the values "development", "staging",
"production", and "test".

### PostgreSQL Configuration

**Connection limit**: Set to 200 in `docker-compose.yaml`. Note that an idle SSE stream
holds *no* Postgres connection (`CONN_MAX_AGE` is unset, so Django's default of 0 applies);
what consumes the 200 is concurrent request-bursts. See `docs/perf/sse-connections.md`.

**Query logging**: Queries >100ms are logged (configured in docker-compose.yaml).

**Request ID tracing**: Every query includes `application_name` with request ID for correlation.

### Static Files

- Collected via `just collectstatic` before Docker image starts
- Served by WhiteNoise with Brotli compression
- No separate web server needed (Daphne serves them)

### Monitoring

**Prometheus metrics**: Exposed at `/metrics` endpoint.

**Pyroscope profiling**: Continuous profiling of Python process (non-macOS).

**Sentry**: Error tracking in production (DSN in `prod_settings.py`).

## Common Patterns

### Adding a New Model Field

1. Edit model in `app/models/*.py`
2. `just makemigrations`
3. Review generated migration in `app/migrations/`
4. `just migrate`
5. Update admin.py if field should be editable in Django admin

### Adding a New SSE Event Type

1. Add the channel name to `app/sse_channels.py`, and a rule for it in
   `can_read_channel()`. Without the rule it is denied, and you will get silence.
2. Add the event name to `SSEEventTypes` in `app/sse_events.py`.
3. If a browser needs it, include the channel in `get_channels_for_request()` so it
   rides the existing connection. **Do not add an endpoint or open a second
   `EventSource`**: browsers allow only six connections per origin, and this project
   spent a while wedged against that limit. See `docs/README.sse.md`.
4. Subscribe by name: `sse-swap="your-event"` on any element inside `<body>`, or
   `window.bridgeEventSource.addEventListener('your-event', handler)` in JavaScript.
5. Add the pair to `SUBSCRIBERS` in `app/test_sse_event_types.py`, so a later rename
   can't quietly disconnect the two halves.

6. If a model change should cause the event, add a broadcaster in `app/broadcast.py` and
   a trigger for it, rather than a `send_event` call in the write path. See
   `docs/README.listen-notify.md`.

See `app/static/app/bridge-game.js` and `app/templates/base.html` for examples.

### Adding a Bot Command

1. Create new management command in `app/management/commands/`
2. Inherit from `BaseCommand`
3. Implement `handle()` method
4. Either work through the ORM directly, or use the API endpoints
   (`/three-way-login/`, `/serialized/hand/<pk>/`, `/call/`, `/play/`)

`app/management/commands/cheating_bot.py` is the bot that ships with the server. It is
*not* an example of an API client: it runs inside the Docker stack, reads the database
directly, and polls in a loop rather than subscribing to SSE. Nothing on the server side
reads SSE any more.

For a client written the way a third party would write one, see
`project/app/reference_client.py` — about a hundred lines of `requests` plus `sseclient`,
exercised against a live server by `project/app/test_reference_client.py`.

## Deployment

### To Production

**Prerequisites**:
- Hetzner VPS setup (see `docs/README.ubuntu-hetz.setup.md`)
- Docker context configured: `docker context create hetz-bridge --docker "host=ssh://ubuntu@<ip>"`
- The working tree must be clean and you must be on `main`; `just prod` checks both and
  refuses otherwise. (`just beta` and `just mini` do not check.)

**Deploy**:
```bash
just prod               # Deploys to hetz-bridge context
```

This:
- Builds the `bridge-django` Docker image once, then reuses it for every service
- Deploys to the remote host via SSH Docker context
- Runs `collectstatic`, `migrate` and `setup_oauth` as one-shot services and waits for
  them, before swapping in the new `django`, `bot`, `clock` and `notifier` containers
- Enables Caddy, which does TLS with automatic Let's Encrypt certificates, and applies the
  rate limits in `caddy/Caddyfile`
- Enables the monitoring profile (Grafana, Prometheus, postgres-exporter, pyroscope)
- Sets `COMPOSE_PROFILES=prod,monitoring`, from which `prod_settings` derives
  `DEPLOYMENT_ENVIRONMENT = "production"`
- Tails the django logs at the end; Ctrl-C there does not stop anything

**Check status**:
```bash
docker context use hetz-bridge
docker compose ps
docker compose logs django --tail=100
```

### Environment Detection

Which settings module you load decides this, not runtime sniffing:
- **"development"**: `dev_settings`, `DEBUG=True` — what `just runme` and `just dev` use
- **"staging"**: `prod_settings` without `prod` in `COMPOSE_PROFILES` — what `just beta`
  and `just mini` use
- **"production"**: `prod_settings` with `COMPOSE_PROFILES` containing `prod` — `just prod`
- **"test"**: `test_settings`, which every test recipe forces

## Troubleshooting

### Auto-reload not working

Django 6.0 has compatibility issues with django-watchfiles. It's commented out of
`dev_settings`. Use Django's built-in reloader (slightly slower but reliable).

**Note**: Static files (CSS/JS) don't trigger server reload - just refresh browser.

### SSE connection issues

`docs/README.sse.md` has a whole section on this; start with the stream-open/close lines
`app/middleware/sse_stream_log.py` writes. A page should show exactly one `/events/all/...`
stream open, plus `/__reload__/events/` in development.

Check Redis is running: `redis-cli ping` should return `PONG`.

### Nothing updates without a page reload

Most likely the `notifier` isn't running: it, not the web process, sends nearly every
event. `docker compose logs notifier --tail=50`. `just runme` starts it in Docker and
prints a warning if it can't; `just notifier` runs it natively against the working tree.

### Bot not responding

Check bot logs: `docker compose logs bot --tail=50`

Verify authentication: `just curl-login` should return player_pk.

### Database connection errors

Ensure PostgreSQL is running:
```bash
just pg-start       # Starts the Postgres container; `just dev` and `just runme` do this too
```

Check credentials match environment variables in `justfile`.
