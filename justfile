set unstable

import 'postgres.just'

# https://just.systems/man/en/chapter_32.html?highlight=xdg#xdg-directories1230

DJANGO_SECRET_DIRECTORY := config_directory() / "info.offby1.bridge"
export DJANGO_SECRET_FILE := DJANGO_SECRET_DIRECTORY / "django_secret_key"
export GOOGLE_OAUTH_CLIENT_ID_FILE := DJANGO_SECRET_DIRECTORY / "google_oauth_client_id"
export GOOGLE_OAUTH_CLIENT_SECRET_FILE := DJANGO_SECRET_DIRECTORY / "google_oauth_client_secret"
export DJANGO_SETTINGS_MODULE := env("DJANGO_SETTINGS_MODULE", "project.dev_settings")
export DOCKER_CONTEXT := env("DOCKER_CONTEXT", if os() == "macos" { "orbstack" } else { "default" })
export HOSTNAME := env("HOSTNAME", `hostname`)

# Put this project's tools ahead of any global ones.  ruff, mypy, pytest, py-spy and
# ipython are all installed in ~/.local/bin too, at versions that need not match ours.
export PATH := justfile_directory() / ".venv" / "bin" + ":" + env("PATH")
export PYTHONUNBUFFERED := "t"

# Settings to use for tests (overrides the default dev_settings)

TEST_DJANGO_SETTINGS := "project.test_settings"
DEV_SERVER_PORT := "9000"

# Helper to run pytest with test settings
[private]
pytest-test *args:
    cd project && DJANGO_SETTINGS_MODULE={{ TEST_DJANGO_SETTINGS }} uv run pytest {{ args }}

[private]
default:
    just --list

[private]
django-secret-directory:
    mkdir -vp "{{ DJANGO_SECRET_DIRECTORY }}"

[parallel]
[private]
[script('bash')]
ensure-django-secret: django-secret-directory
    set -euo pipefail
    touch "{{ DJANGO_SECRET_FILE }}"
    if [ ! -f "{{ DJANGO_SECRET_FILE }}" -o $(gstat --format=%s "{{ DJANGO_SECRET_FILE }}") -lt 50 ]
    then
    python3  -c 'import secrets; print(secrets.token_urlsafe(100))' > "{{ DJANGO_SECRET_FILE }}"
    fi

# Detect "hoseage" caused by me running "orb shell" and building for Ubuntu in this very directory.
[private]
[script('bash')]
die-if-virtualenv-remarkably-hosed:
    set -euo pipefail

    # I suspect the below craziness only pertains to MacOS.
    if [ "{{ os() }}" != "macos" ]
    then
    exit 0
    fi

    # If it don't exist, it can't be hosed :-)
    if [ ! -d .venv ]
    then
    exit 0
    fi

    p=.venv/bin/python
    if [ ! -h ${p} ]
    then
    echo "How come you don't have a symlink named ${p}"
    exit 1
    fi

    case $(/bin/realpath -q ${p}) in
       ""|/usr/bin/python*)
        echo oh noes! your virtualenv python is bogus
        ls -l ${p}
        echo I bet you were running an orb machine
        echo 'May I recommend "just clean"?'
        exit 1
    esac

[group('virtualenv')]
uv-install: uv-install-no-dev
    uv sync --quiet

[group('virtualenv')]
uv-install-no-dev:
    uv sync --quiet --no-dev

mypy: uv-install ty
    uv run dmypy run -- .

# Not yet useful, but probably will be soon
ty: uv-install
    uvx ty check --quiet --extra-search-path project --extra-search-path stubs || true

alias version := version-file

[private]
version-file:
    git log -1 --format='%h %cs' > project/VERSION
    -git symbolic-ref HEAD > project/GIT_SYMBOLIC_REF

[private]
pre-commit:
    -pre-commit install  --hook-type pre-commit --hook-type pre-push

[group('django')]
[parallel]
[private]
all-but-django-prep: pre-commit uv-install pg-start redis

[group('django')]
[parallel]
[private]
manage *options: all-but-django-prep ensure-django-secret version-file
    cd project && uv run python manage.py {{ options }}

[group('django')]
[script('bash')]
collectstatic:
    set -euxo pipefail
    mkdir -p project/static_root
    cd project && uv run python manage.py collectstatic --no-input --clear && touch static_root/.gitkeep

[group('django')]
fixture *options: pg-stop drop migrate (manage "loaddata " + options) (manage "update_redundant_fields")
    @echo To create a new fixture, do e.g. "just dumpdata"

alias load := fixture
alias loaddata := fixture

[group('django')]
dumpdata: all-but-django-prep ensure-django-secret version-file
    just --no-deps manage dumpdata app auth | jq | ./redact-secrets.sh > {{ datetime_utc("%FT%T%z") }}.json
    @echo Now move that file to project/app/fixtures

# You can add  --print-sql-location to see a stack trace on *every* *damned* *query* :-)
[group('django')]
shell: migrate (manage "shell_plus --print-sql ")

# Like "shell", but has no dependencies, so starts up fast (if stuff is already built).
[group('django')]
sp:
    cd project && uv run python manage.py shell_plus --print-sql

[group('django')]
makemigrations *options: (manage "makemigrations " + options)

[group('django')]
migrate: makemigrations create-cache (manage "migrate")

# Whop docker upside the haid -- in an attempt to prevent "failed to set up container networking: network blahblah not found"

# See `why-whop.md`
[group('docker')]
whop:
    docker compose down
    docker network prune --force

[group('stress')]
stress *options:
    docker compose exec django /bridge/.venv/bin/python manage.py big_bot_stress {{ options }}

# TODO -- embed the docker context, or some similar discriminator, into the name of the log file, so that I can tell
# where the logs came from.
dump:
    docker compose logs django > django-{{ datetime_utc("%FT%T%z") }}

dump-bot:
    docker compose logs bot > bot-{{ datetime_utc("%FT%T%z") }}

# Caddy's interesting log lines: rate-limit rejections and anything at warn or
# above. Caddy writes JSON to stderr and Docker captures it, so there is no log file
# to collect and nothing to ship anywhere -- this recipe just filters and reformats
# what `docker compose logs caddy` already has. Its `ts` field is epoch seconds,
# which this turns into UTC.
#
# The rate limiter logs a rejection at *info* level, and the line carries no HTTP
# status, so neither a level filter nor a search for "429" finds it. It looks like:
#
#   {"level":"info","ts":1787333972.2284505,"logger":"http.handlers.rate_limit",
#    "msg":"rate limit exceeded","zone":"list_views","wait":0.047427378,
#    "remote_ip":"200.195.79.237"}
#
# Hence the match on the logger name. Note `remote_ip` sits at the top level here,
# whereas an access-log entry nests it under `.request`.
#
# Takes `docker compose logs` options, so: `just caddy-log --since 1h`,
# `just caddy-log --follow`, `just caddy-log --tail 500`.
#
# For the raw lines, including the info-level ones this drops, run
# `docker compose logs caddy` directly.
[group('docker')]
[script('bash')]
caddy-log *options:
    set -euo pipefail

    # --no-log-prefix: without it every line arrives as "caddy-1  | {...}" and jq
    # can't parse it. --raw-input plus `fromjson?` skips the handful of non-JSON
    # lines Caddy emits before its logger is configured, instead of dying on them.
    docker compose logs caddy --no-log-prefix {{ options }} |
        jq --raw-input --raw-output --unbuffered '
            fromjson?
            | select(.logger == "http.handlers.rate_limit"
                     or .level == "warn" or .level == "error"
                     or .status == 429 or (.status // 0) >= 500)
            | [ (.ts | floor | todate)
              , .level
              , (.logger // "-")
              , (.remote_ip // .request.remote_ip // "-")
              , (if .zone then "zone=\(.zone)" else empty end)
              , (if .wait then "wait=\(.wait * 1000 | round)ms" else empty end)
              , (if .status then "status=\(.status)" else empty end)
              , (if .request then "\(.request.method) \(.request.host)\(.request.uri)" else empty end)
              , "\"\(.msg)\""
              , (if .error then "error=\"\(.error)\"" else empty end)
              ]
            | join(" ")
        '

setup-oauth: migrate (manage "setup_oauth")

[group('development')]
[script('bash')]
_notests *options: version-file django-superuser migrate create-cache ensure-django-secret
    set -euxo pipefail

    # Pre-flight check: fail cleanly if port is already in use
    set +x  # Turn off command echo for cleaner error messages
    if ! python3 -c "import socket; s = socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); s.bind(('127.0.0.1', {{ DEV_SERVER_PORT }})); s.close()" 2>/dev/null; then
        echo "ERROR: Port {{ DEV_SERVER_PORT }} is already in use!"
        echo "Possible causes:"
        echo "  - Docker stack is running: Check with 'docker compose ps'"
        echo "  - Another dev server is running"
        echo "To fix:"
        echo "  - Stop Docker: 'docker compose down'"
        echo "  - Or kill the process using port {{ DEV_SERVER_PORT }}"
        exit 1
    fi
    set -x  # Re-enable command echo

    # Run the change-notifier in Docker (like postgres and redis), so there's a
    # single notifier servicing this database. --build keeps the image in sync
    # with the working tree (runme already runs the tests, so the cached rebuild
    # is negligible); the advisory lock makes a redundant start harmless. The
    # container needs the same secret env that _deploy sets up.
    export DJANGO_SECRET_KEY=$(cat "${DJANGO_SECRET_FILE}")
    export GOOGLE_OAUTH_CLIENT_ID=$(cat "${GOOGLE_OAUTH_CLIENT_ID_FILE:-/dev/null}" 2>/dev/null || echo "")
    export GOOGLE_OAUTH_CLIENT_SECRET=$(cat "${GOOGLE_OAUTH_CLIENT_SECRET_FILE:-/dev/null}" 2>/dev/null || echo "")
    export GIT_VERSION="$(cat project/VERSION)"
    docker compose up --detach --build notifier || echo "WARNING: couldn't start the docker notifier; live updates may not flow"

    cd project
    uv run python manage.py runserver {{ DEV_SERVER_PORT }} {{ options }}

[group('development')]
[parallel]
[script('bash')]
runme *options: ft (_notests options)

alias runserver := runme

# Run the notifier natively against the working tree -- for iterating on
# broadcast code with live reload. Stops the Docker notifier first so this one
# wins the advisory lock; the next `just runme`/`just dev` brings the Docker one back.
[group('development')]
[script('bash')]
notifier: all-but-django-prep ensure-django-secret version-file migrate
    docker compose stop notifier || true
    cd project && uv run python manage.py notifier

[parallel]
curl *options: django-superuser migrate create-cache ensure-django-secret
    curl -v --cookie cook --cookie-jar cook "{{ options }}"

[script('bash')]
curl-login:
    set -euxo pipefail
    b64_blob=$(echo -n bob:. | base64)
    header="Authorization: Basic ${b64_blob}"
    curl --cookie cook --cookie-jar cook --header "${header}" http://localhost:{{ DEV_SERVER_PORT }}/login/

create-cache: (manage "createcachetable")

alias createsuperuser := django-superuser
alias superuser := django-superuser

[group('django')]
django-superuser: all-but-django-prep migrate (manage "create_insecure_superuser")

# Run tests with --exitfirst and --failed-first
[group('development')]
t *options: makemigrations mypy (test "--exitfirst --failed-first " + options)

# Run individual tests with no dependencies
k *options:
    just pytest-test --exitfirst --failed-first --showlocals -s --log-cli-level=DEBUG -vv -k {{ options }}

# Draw a nice entity-relationship diagram
[group('django')]
graph: migrate
    cd project && uv run python manage.py graph_models --no-inheritance app | dot -Tsvg > $TMPDIR/graph.svg
    open $TMPDIR/graph.svg

# Run all the tests
[group('development')]
[script('bash')]
test *options: makemigrations mypy collectstatic setup-oauth
    set -euxo pipefail
    export DJANGO_SETTINGS_MODULE={{ TEST_DJANGO_SETTINGS }}
    cd project

    pytest_args="--create-db --log-cli-level=WARNING {{ options }}"

    case "${PYINSTRUMENT:-}" in
    t*)
      pyinstrument_exe={{ justfile_dir() }}/.venv/bin/pyinstrument
      uv run coverage run --rcfile={{ justfile_dir() }}/pyproject.toml --branch ${pyinstrument_exe} -m pytest ${pytest_args}
    ;;
    *)
      pytest_exe={{ justfile_dir() }}/.venv/bin/pytest
      uv run coverage run --rcfile={{ justfile_dir() }}/pyproject.toml --branch ${pytest_exe} ${pytest_args}
    ;;
    esac

# Fast tests (i.e., run in parallel)
[group('development')]
ft *options: (t "-n 8 " + options)

# Run UI tests with Playwright (visible browser)
[group('development')]
ui-test *options:
    just pytest-test -m playwright --headed {{ options }}

# Run UI tests in headless mode (faster, for CI)
[group('development')]
ui-test-headless *options:
    just pytest-test -m playwright {{ options }}

# Run UI tests on mobile viewport
[group('development')]
ui-test-mobile *options:
    just pytest-test -m playwright --headed --device='"iPhone 12"' {{ options }}

# Display coverage from a test run
[group('development')]
[script('bash')]
cover *options: (test options)
    set -euox pipefail
    cd project
    uv run coverage html --rcfile={{ justfile_dir() }}/pyproject.toml --show-contexts
    open htmlcov/index.html

# Nix the virtualenv and anything not checked in to git, but leave the database.
[script('bash')]
clean:
    git clean -dxff

[parallel]
[private]
docker-prerequisites: version-file orb uv-install-no-dev ensure-django-secret start

alias dc := dcu

dcu:
    @echo Use "just dev" now ; false

ensure-git-repo-clean:
    [[ -z "$(git status --porcelain)" ]]

ensure-branch-is-main:
    [[ "$(git symbolic-ref HEAD)" = "refs/heads/main" ]]

[private]
prod-deploy-prerequisites: docker-prerequisites ensure-branch-is-main ensure-git-repo-clean

[continue]
[private]
[script('bash')]
_deploy hostname profile context settings_module *options:
    set -euo pipefail

    export CADDY_HOSTNAME="{{ hostname }}"
    export COMPOSE_PROFILES={{ profile }} # prod and beta get caddy + monitoring; dev doesn't
    export DOCKER_CONTEXT={{ context }}   # roughly equivalent to hostname, except for "default"
    export DJANGO_SECRET_KEY=$(cat "${DJANGO_SECRET_FILE}")
    export DJANGO_SETTINGS_MODULE={{ settings_module }}
    export GIT_VERSION="$(cat project/VERSION)"

    # Google OAuth credentials (optional - gracefully handles if files don't exist)
    export GOOGLE_OAUTH_CLIENT_ID=$(cat "${GOOGLE_OAUTH_CLIENT_ID_FILE:-/dev/null}" 2>/dev/null || echo "")
    export GOOGLE_OAUTH_CLIENT_SECRET=$(cat "${GOOGLE_OAUTH_CLIENT_SECRET_FILE:-/dev/null}" 2>/dev/null || echo "")

    # Reclaim what the previous deploy left behind, before we need the room. Every
    # deploy replaces the `bridge-django` (and caddy/grafana/prometheus) tags, and the
    # images they used to point at stay on disk as untagged `<none>` layers forever.
    # On 2026-08-29 that had filled hetz-bridge's 75G disk: 324 images of which 9 were
    # in use, plus 21G of build cache, and `uv sync` died with ENOSPC mid-build.
    # `image prune` without `-a` removes only untagged images, so anything a container
    # references -- including the stack that is still serving traffic right now -- stays.
    docker image prune --force
    docker builder prune --force --max-used-space=10GB

    # Ensure the stuff that we depend on is up to date
    docker compose pull --ignore-buildable

    # Build the shared bridge-django image ONCE. Building it via all five django-*
    # services in parallel makes them race to export the same tag (buildkit:
    # image "bridge-django:latest" already exists), so build only `django` here.
    # The distinct caddy/grafana/prometheus images are built at `up` time (--build) below.
    docker compose build django

    docker compose up --detach --wait postgres redis # only needed when those services aren't already running

    # Run one-shot setup services (migrations, collectstatic, oauth) with the new image
    docker compose up --detach --no-deps django-collected-static django-migrated django-oauth-setup
    docker compose wait                  django-collected-static django-migrated django-oauth-setup

    # Swap in the new django container (and bot, clock, and notifier); --no-deps avoids
    # restarting postgres/redis/caddy
    just dump
    docker compose up --detach --no-deps --force-recreate django bot clock notifier {{ options }}

    # Bring up Caddy when its profile is active (prod/beta). Like the monitoring block below,
    # `_deploy` only ups named services, so Caddy needs an explicit `up` -- without this a fresh
    # host never starts it (older hosts only kept it alive via restart:unless-stopped).
    if [[ ",${COMPOSE_PROFILES:-}," == *",prod,"* || ",${COMPOSE_PROFILES:-}," == *",beta,"* ]]; then
        docker compose up --detach --build --force-recreate caddy
    fi

    # Bring up the monitoring stack when its profile is active (prod/beta).  `_deploy` only ups
    # named services, so these need an explicit `up`; the guard keeps them off in dev.
    # --force-recreate reattaches them to the current network, in case they're stranded leftovers.
    if [[ ",${COMPOSE_PROFILES:-}," == *",monitoring,"* ]]; then
        docker compose up --detach --build --force-recreate grafana prometheus postgres-exporter pyroscope
    fi

    docker compose logs django --follow || true

[group('deploy')]
prod: prod-deploy-prerequisites && (_deploy "bridge.offby1.info" "prod,monitoring" "hetz-bridge" "project.prod_settings")

[group('deploy')]
beta: docker-prerequisites && (_deploy "beta.bridge.offby1.info" "beta,monitoring" "hetz-bridge-beta" "project.prod_settings")

[group('deploy')]
dev *options: docker-prerequisites whop && (_deploy "localhost" "dev" "default" "project.dev_settings" options)

# Like `just dev`, but also brings up the monitoring stack (grafana/prometheus/&c.) locally.
[group('deploy')]
dev-monitoring *options: (dev "grafana prometheus postgres-exporter pyroscope " + options)

[group('deploy')]
mini: docker-prerequisites && (_deploy "erics-mac-mini.tail571dc2.ts.net" "beta,monitoring" "mini" "project.prod_settings")

# `tailscale serve` persists on the host and is idempotent, so this is a one-time-per-host setup.
# Override the host for beta: `just tailscale-serve root@hetz-bridge-beta`.
# Expose Grafana (3000) and Prometheus (9090) to the tailnet on a deployed host via Tailscale SSH.
[group('deploy')]
tailscale-serve ssh_host="root@hetz-bridge":
    ssh {{ ssh_host }} 'tailscale serve --bg --tcp 3000 tcp://127.0.0.1:3000 \
        && tailscale serve --bg --tcp 9090 tcp://127.0.0.1:9090 \
        && tailscale serve status'

# Kill it all.  Kill it all, with fire.
nuke: clean docker-nuke
