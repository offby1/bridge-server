# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an online Bridge card game server built with Django 6.0. It supports both human players (via web UI) and AI bots (via REST API), with real-time game updates delivered through Server-Sent Events (SSE).

## Essential Commands

All commands use [Just](https://just.systems/) command runner. See `justfile` for complete list.

### Development
```bash
just runme              # Start Django dev server on localhost:9000 (native, no Docker)
just dcu                # Start full Docker Compose stack (Django + Postgres + Redis + Bots)
just shell              # Django shell with pre-populated queries
just sp                 # Quick shell_plus (no dependencies)
```

### Testing
```bash
just test               # Full test suite with coverage report (HTML in htmlcov/)
just ft                 # Fast tests (parallel, 8 workers via pytest-xdist)
just t                  # Tests with exitfirst and failed-first
just k <pattern>        # Run specific test by name (e.g., just k hand_events)
just mypy               # Type checking with dmypy daemon

# UI Tests (Playwright)
just ui-test-headless   # Run UI tests headless (PREFERRED - won't interfere with laptop use)
just ui-test            # Run UI tests headed (visible browser - avoid during active work)
just ui-test-mobile     # Run UI tests with mobile viewport (headed)
```

**Important**: Always use `just ui-test-headless` for UI tests unless specifically debugging browser behavior visually. Headless mode allows laptop use during test runs without interference.

### Database
```bash
just migrate            # Run migrations
just makemigrations     # Create new migrations
just dumpdata           # Export DB to fixture JSON
just load <fixture>     # Import fixture (drops DB first)
just graph              # Generate ER diagram (opens in browser)
```

### Deployment
```bash
just prod               # Deploy to production (requires hetz-bridge Docker context)
just beta               # Deploy to beta.bridge.offby1.info
```

## Architecture

### Technology Stack

- **Framework**: Django 6.0 with Daphne ASGI server (async support)
- **Database**: PostgreSQL 17 (max_connections=200 for SSE clients)
- **Cache/PubSub**: Redis (django-eventstream backend)
- **Real-time**: Server-Sent Events (SSE) via django-eventstream
- **Package Manager**: UV (not pip/poetry)
- **Python**: 3.12-3.13 required

### Settings Structure

Three-tier configuration pattern:

1. **`project/base_settings.py`** - Common settings
2. **`project/dev_settings.py`** - Development (DEBUG=True, browser reload)
3. **`project/prod_settings.py`** - Production (Sentry, hardened security)

Set via `DJANGO_SETTINGS_MODULE` environment variable. The `justfile` exports this automatically.

### Real-Time Event Architecture

**Critical Pattern**: All game state updates flow through django-eventstream → Redis → SSE to clients.

#### Channel Manager (`app/channelmanager.py`)
Custom `MyChannelManager` controls SSE channel access:

- **`lobby`** - Broadcast to all logged-in users
- **`player:html:hand:{player_pk}`** - Private HTML hand updates for web UI
- **`player:json:{player_pk}`** - Private JSON transcripts for bots
- **`table:html:{hand_pk}`** - Table-wide updates (auction, tricks)
- **`chat:player-to-player:{channel}`** - Encrypted P2P messages

#### How to Send Events
```python
from django_eventstream import send_event

# Send to a player's private channel
send_event(
    f"player:html:hand:{player.pk}",
    "message",
    {"bidding_box_html": rendered_html}
)

# Send to everyone at a table
send_event(
    f"table:html:{hand.pk}",
    "message",
    {"trick_counts_string": "NS: 3, EW: 2"}
)
```

Clients subscribe via GET `/events/<channel>/` and receive SSE streams.

### Game Logic Organization

#### Core Models (`app/models/`)

**`hand.py`** (~2000 lines) - Most complex model
- Tracks auction state (calls made, contract determination)
- Tracks play state (cards played, tricks won, completion)
- Contains card distribution for all four players
- Uses JSONField for calls/plays history (append-only)
- Key methods: `call()`, `play()`, `distribute_cards()`, `determine_contract()`

**`player.py`** (~500 lines)
- Links User to Player (one-to-one)
- Tracks current hand assignment
- Partnership management (north/south vs east/west)
- Bot flag (`is_synthetic`, `allow_bot_to_play_for_me`)

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

### View Patterns

#### Hand Visibility Rules (`app/views/hand.py`)

The `display_skeleton()` function implements Bridge visibility rules:

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

# 4. Make a call
curl -b cookies.txt -X POST \
  -H "X-CSRFToken: <from-cookie>" \
  -d "call=1%E2%99%A3" \
  http://localhost:9000/call/123/

# 5. Play a card
curl -b cookies.txt -X POST \
  -H "X-CSRFToken: <from-cookie>" \
  -d "card=%E2%99%A52" \
  http://localhost:9000/play/123/
```

**CSRF Protection**: POST requests require either:
- `X-CSRFToken` header with csrftoken cookie value, OR
- `csrfmiddlewaretoken` form field

See `docs/README.api.md` for complete API documentation.

### Middleware Stack

Custom middleware in `app/middleware/`:

- **RequestIDMiddleware** - Adds `X-Request-Id` for tracing (propagated to PostgreSQL logs)
- **AddVersionHeaderMiddleware** - Includes git commit in `X-Bridge-Version` header
- **PrometheusBeforeMiddleware/AfterMiddleware** - Request metrics
- **SwallowAnnoyingExceptionMiddleware** - Suppresses known harmless errors (e.g., SSE client disconnects)

All middleware is registered in order in `base_settings.py`.

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
just fixture app            # Optional: Load sample tournament/players
```

### Running Locally

**Native (no Docker)**:
```bash
just runme                  # Starts on localhost:9000
```
This automatically:
- Generates secrets if missing
- Runs migrations
- Creates superuser if needed
- Starts dev server with auto-reload

**Docker Compose Stack**:
```bash
just dcu
```
Includes: Django, PostgreSQL, Redis, bot player, Prometheus, Grafana, Pyroscope profiler.

### Testing Patterns

Tests use pytest with Django fixtures.

**Run specific test**:
```bash
just k test_hand_distribution    # By function name
just k "test_hand and auction"   # Pattern matching
```

**Parallel testing**: `just ft` uses 8 workers via pytest-xdist. Disable with `-n 0` for debugging.

**Coverage**: `just test` generates HTML report in `htmlcov/`. Open `htmlcov/index.html` in browser.

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
just drop           # Docker only
just migrate        # Recreate schema
just fixture app    # Reload sample data
```

### Performance Testing

```bash
just stress --tiny --tempo=1.0     # Small stress test, normal speed
just stress --tempo=0              # Maximum speed (no delays)
just perf-local                    # 100 players, production settings locally
```

Bots will automatically join games and play hands. Monitor with `just logs`.

## Important Configuration

### Environment Variables

Set by `justfile` or Docker Compose:

- **`DJANGO_SETTINGS_MODULE`** - Which settings file (dev_settings/prod_settings)
- **`DJANGO_SECRET_FILE`** - Path to SECRET_KEY file
- **`DJANGO_SKELETON_KEY_FILE`** - Path to API skeleton key
- **`PGHOST`**, **`PGUSER`**, **`PGPASS`** - PostgreSQL connection
- **`REDIS_HOST`** - Redis server (default: localhost)
- **`DEPLOYMENT_ENVIRONMENT`** - "development", "staging", or "production"

### PostgreSQL Configuration

**Connection limit**: Set to 200 in `docker-compose.yaml` to support many SSE clients.

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

1. Define channel name in `app/channelmanager.py:can_read_channel()`
2. Send events using `send_event(channel, "message", data_dict)`
3. Subscribe in JavaScript: `new EventSource('/events/{channel}/')`
4. Add event listener: `eventSource.addEventListener('message', handler)`

See `app/templates/interactive_hand.html` for JavaScript SSE examples.

### Adding a Bot Command

1. Create new management command in `app/management/commands/`
2. Inherit from `BaseCommand`
3. Implement `handle()` method
4. Use API endpoints (`/three-way-login/`, `/serialized/hand/`, `/call/`, `/play/`)
5. Subscribe to SSE for asynchronous updates

See `app/management/commands/cheating_bot.py` for reference implementation.

## Deployment

### To Production

**Prerequisites**:
- Hetzner VPS setup (see `docs/README.ubuntu-hetz.setup.md`)
- Docker context configured: `docker context create hetz-bridge --docker "host=ssh://ubuntu@<ip>"`

**Deploy**:
```bash
just prod               # Deploys to hetz-bridge context
```

This:
- Builds Docker image
- Deploys to remote host via SSH Docker context
- Enables Caddy reverse proxy with automatic Let's Encrypt TLS
- Sets `DEPLOYMENT_ENVIRONMENT=production`

**Check status**:
```bash
docker context use hetz-bridge
docker compose ps
docker compose logs django --tail=100
```

### Environment Detection

The app auto-detects environment:
- **"development"**: `DEBUG=True`, no Docker
- **"staging"**: Docker locally (via `just dcu`)
- **"production"**: Docker with `COMPOSE_PROFILES=prod` (via `just prod`)

## Troubleshooting

### Auto-reload not working

Django 6.0 has compatibility issues with django-watchfiles. It's disabled in dev_settings. Use Django's built-in reloader (slightly slower but reliable).

**Note**: Static files (CSS/JS) don't trigger server reload - just refresh browser.

### SSE connection issues

Check Redis is running: `redis-cli ping` should return `PONG`.

Check PostgreSQL connection limit: `SELECT count(*) FROM pg_stat_activity;` should be <200.

### Bot not responding

Check bot logs: `docker compose logs bot --tail=50`

Verify authentication: `just curl-login` should return player_pk.

### Database connection errors

Ensure PostgreSQL is running:
```bash
# Native: just pg-start
# Docker: just dcu includes PostgreSQL
```

Check credentials match environment variables in `justfile`.
