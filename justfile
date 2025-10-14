set unstable := true

import 'postgres.just'

# https://just.systems/man/en/chapter_32.html?highlight=xdg#xdg-directories1230

DJANGO_SECRET_DIRECTORY := config_directory() / "info.offby1.bridge"
export DJANGO_SECRET_FILE := DJANGO_SECRET_DIRECTORY / "django_secret_key"
export DJANGO_SETTINGS_MODULE := env("DJANGO_SETTINGS_MODULE", "project.dev_settings")
export DJANGO_SKELETON_KEY_FILE := DJANGO_SECRET_DIRECTORY / "django_skeleton_key"
export DOCKER_CONTEXT := env("DOCKER_CONTEXT", if os() == "macos" { "orbstack" } else { "default" })
export HOSTNAME := env("HOSTNAME", `hostname`)
export PYTHONUNBUFFERED := "t"

[private]
default:
    just --list

[private]
django-secret-directory:
    mkdir -vp "{{ DJANGO_SECRET_DIRECTORY }}"

[private]
[script('bash')]
ensure-django-secret: django-secret-directory
    set -euo pipefail
    touch "{{ DJANGO_SECRET_FILE }}"
    if [ ! -f "{{ DJANGO_SECRET_FILE }}" -o $(gstat --format=%s "{{ DJANGO_SECRET_FILE }}") -lt 50 ]
    then
    python3  -c 'import secrets; print(secrets.token_urlsafe(100))' > "{{ DJANGO_SECRET_FILE }}"
    fi

[parallel]
[private]
[script('bash')]
ensure-skeleton-key: uv-install-no-dev ensure-django-secret
    set -euo pipefail
    touch "{{ DJANGO_SKELETON_KEY_FILE }}"
    if [ ! -f "{{ DJANGO_SKELETON_KEY_FILE }}" -o $(gstat --format=%s "{{ DJANGO_SKELETON_KEY_FILE }}") -lt 50 ]
    then
    cd project && uv run python manage.py generate_secret_key > "{{ DJANGO_SKELETON_KEY_FILE }}"
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
    uvx ty check --quiet --extra-search-path project || true

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
manage *options: all-but-django-prep ensure-skeleton-key version-file
    cd project && uv run python manage.py {{ options }}

[group('django')]
collectstatic: (manage "collectstatic --no-input")

[group('django')]
fixture *options: pg-stop drop migrate (manage "loaddata " + options) (manage "update_redundant_fields")
    @echo To create a new fixture, do e.g. "just dumpdata"

alias load := fixture
alias loaddata := fixture

[group('django')]
dumpdata: all-but-django-prep ensure-skeleton-key version-file
    just --no-deps manage dumpdata app auth | jq > {{ datetime_utc("%FT%T%z") }}.json
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
[group('docker')]
whop:
    docker compose down
    docker network prune --force

[group('stress')]
stress *options:
    docker compose exec django /bridge/.venv/bin/python manage.py big_bot_stress {{ options }}

dump:
    docker compose logs django > django-{{ datetime_utc("%FT%T%z") }}

dump-bot:
    docker compose logs bot > bot-{{ datetime_utc("%FT%T%z") }}

[group('stress')]
[script('bash')]
tiny:
    set -euxo pipefail

    just drop
    DJANGO_SETTINGS_MODULE=project.prod_settings just dcu -d
    just stress --tiny --tempo=0
    docker compose logs django bot --follow

[group('development')]
[parallel]
[script('bash')]
runme *options: ft version-file django-superuser migrate create-cache ensure-skeleton-key
    set -euxo pipefail
    cd project
    uv run python manage.py runserver 9000 {{ options }}

alias runserver := runme

[parallel]
curl *options: django-superuser migrate create-cache ensure-skeleton-key
    curl -v --cookie cook --cookie-jar cook "{{ options }}"

[script('bash')]
curl-login:
    set -euxo pipefail
    b64_blob=$(echo -n bob:. | base64)
    header="Authorization: Basic ${b64_blob}"
    curl --cookie cook --cookie-jar cook --header "${header}" http://localhost:9000/three-way-login/

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
    cd project && uv run pytest --exitfirst --failed-first --showlocals -s --log-cli-level=DEBUG  -vv -k {{ options }}

# Draw a nice entity-relationship diagram
[group('django')]
graph: migrate
    cd project && uv run python manage.py graph_models --no-inheritance app | dot -Tsvg > $TMPDIR/graph.svg
    open $TMPDIR/graph.svg

# Run all the tests
[group('development')]
[script('bash')]
test *options: makemigrations mypy collectstatic
    set -euxo pipefail
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
docker-prerequisites: version-file orb uv-install-no-dev ensure-skeleton-key start

# typical usage: just nuke ; docker volume prune --all --force ; just dcu
[group('development')]
[script('bash')]
dc *options: docker-prerequisites
    set -euo pipefail

    export DJANGO_SECRET_KEY=$(cat "${DJANGO_SECRET_FILE}")
    export DJANGO_SKELETON_KEY=$(cat "${DJANGO_SKELETON_KEY_FILE}")
    export GIT_VERSION="$(cat project/VERSION)"

    tput rmam                   # disables line wrapping
    trap "tput smam" EXIT       # re-enables line wrapping when this little bash script exits

    docker compose {{ options }}

dcu *options: (dc "up --build " + options)

alias perf := perf-local

[group('development')]
[group('perf')]
[script('bash')]
perf-local: drop docker-prerequisites
    set -euo pipefail

    export DJANGO_SECRET_KEY=$(cat "${DJANGO_SECRET_FILE}")
    export DJANGO_SETTINGS_MODULE=project.prod_settings
    export DJANGO_SKELETON_KEY=$(cat "${DJANGO_SKELETON_KEY_FILE}")
    export GIT_VERSION="$(cat project/VERSION)"

    tput rmam                   # disables line wrapping
    trap "tput smam" EXIT       # re-enables line wrapping when this little bash script exits

    just whop
    docker compose up --build --detach
    just stress --min-players=100 --tempo=0.5
    docker compose logs django --follow

# Your kids know 'front and follow'?
[script('bash')]
follow: (dcu "--watch")

ensure-git-repo-clean:
    [[ -z "$(git status --porcelain)" ]]

ensure-branch-is-main:
    [[ "$(git symbolic-ref HEAD)" = "refs/heads/main" ]]

[private]
deploy-prerequisites: docker-prerequisites ensure-branch-is-main ensure-git-repo-clean

[group('deploy')]
[script('bash')]
prod: deploy-prerequisites
    set -euo pipefail

    export CADDY_HOSTNAME=bridge.offby1.info
    export COMPOSE_PROFILES=prod
    export DJANGO_SECRET_KEY=$(cat "${DJANGO_SECRET_FILE}")
    export DJANGO_SETTINGS_MODULE=project.prod_settings
    export DJANGO_SKELETON_KEY=$(cat "${DJANGO_SKELETON_KEY_FILE}")
    export DOCKER_CONTEXT=hetz-prod
    export GIT_VERSION="$(cat project/VERSION)"

    docker compose up --build --detach
    docker compose logs django --follow

[group('deploy')]
[script('bash')]
beta: docker-prerequisites
    set -euo pipefail

    export CADDY_HOSTNAME=beta.bridge.offby1.info
    export COMPOSE_PROFILES=prod
    export DJANGO_SECRET_KEY=$(cat "${DJANGO_SECRET_FILE}")
    export DJANGO_SETTINGS_MODULE=project.prod_settings
    export DJANGO_SKELETON_KEY=$(cat "${DJANGO_SKELETON_KEY_FILE}")
    export DOCKER_CONTEXT=hetz-beta
    export GIT_VERSION="$(cat project/VERSION)"

    docker compose up --build --detach
    docker compose logs django --follow

[group('deploy')]
[script('bash')]
mini: docker-prerequisites
    set -euox pipefail

    export COMPOSE_PROFILES=prod
    export DJANGO_SECRET_KEY=$(cat "${DJANGO_SECRET_FILE}")
    export DJANGO_SETTINGS_MODULE=project.prod_settings
    export DJANGO_SKELETON_KEY=$(cat "${DJANGO_SKELETON_KEY_FILE}")
    export DOCKER_CONTEXT=mini
    export GIT_VERSION="$(cat project/VERSION)"

    docker compose up --build --detach
    docker compose logs django --follow

# Kill it all.  Kill it all, with fire.
nuke: clean docker-nuke
