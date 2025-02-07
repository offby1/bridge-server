set unstable := true

import 'postgres.just'

# https://just.systems/man/en/chapter_32.html?highlight=xdg#xdg-directories1230

export DJANGO_SECRET_FILE := config_directory() / "info.offby1.bridge/django_secret_key"
export DJANGO_SKELETON_KEY_FILE := config_directory() / "info.offby1.bridge/django_skeleton_key"
export DJANGO_SETTINGS_MODULE := env("DJANGO_SETTINGS_MODULE", "project.dev_settings")
export DOCKER_CONTEXT := env("DOCKER_CONTEXT", "orbstack")
export HOSTNAME := env("HOSTNAME", `hostname`)
export PYTHONUNBUFFERED := "t"

[private]
default:
    just --list

[private]
[script('bash')]
ensure-django-secret:
    set -euo pipefail
    mkdir -vp "$(dirname {{ DJANGO_SECRET_FILE }})"
    touch "{{ DJANGO_SECRET_FILE }}"
    if [ ! -f "{{ DJANGO_SECRET_FILE }}" -o $(stat --format=%s "{{ DJANGO_SECRET_FILE }}") -lt 50 ]
    then
    python3  -c 'import secrets; print(secrets.token_urlsafe(100))' > "{{ DJANGO_SECRET_FILE }}"
    else
    echo "Looks like you've already got a reasonable django secret already: "; ls -l "{{ DJANGO_SECRET_FILE }}"
    fi

[private]
[script('bash')]
ensure-skeleton-key: poetry-install-no-dev ensure-django-secret
    set -euo pipefail
    mkdir -vp "$(dirname {{ DJANGO_SKELETON_KEY_FILE }})"
    touch "{{ DJANGO_SKELETON_KEY_FILE }}"
    if [ ! -f "{{ DJANGO_SKELETON_KEY_FILE }}" -o $(stat --format=%s "{{ DJANGO_SKELETON_KEY_FILE }}") -lt 50 ]
    then
    cd project && poetry run python manage.py generate_secret_key > "{{ DJANGO_SKELETON_KEY_FILE }}"
    else
    echo "Looks like you've already got a reasonable skeleton key already: "; ls -l "{{ DJANGO_SKELETON_KEY_FILE }}"
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

[private]
[script('bash')]
die-if-poetry-active:
    if [[ -n "${POETRY_ACTIVE:-}" || -n "${VIRTUAL_ENV:-}" ]]
    then
      if [[ -n "${VSCODE_ENV_REPLACE:-}" ]]
         then echo "I guess this is VSC; let's soldier on and see what happens"
      else
        echo Hey man some environment variables suggest that a virtualenv is active
        env | sort | grep --extended "POETRY_ACTIVE|VIRTUAL_ENV"

        false
      fi
    fi

[group('virtualenv')]
lock: die-if-poetry-active die-if-virtualenv-remarkably-hosed
    poetry lock

[group('virtualenv')]
poetry-install: poetry-install-no-dev
    poetry install

[group('virtualenv')]
poetry-install-no-dev: die-if-poetry-active lock
    poetry install --without=dev

mypy: poetry-install
    poetry run mypy . --exclude=/migrations/

alias version := version-file

[private]
version-file:
    git log -1 --format='%h %cs' > project/VERSION
    git symbolic-ref HEAD > project/GIT_SYMBOLIC_REF

[private]
pre-commit:
    -pre-commit install  --hook-type pre-commit --hook-type pre-push

[group('django')]
[private]
all-but-django-prep: version-file pre-commit poetry-install pg-start

[group('django')]
[private]
manage *options: all-but-django-prep ensure-skeleton-key
    cd project && poetry run python manage.py {{ options }}

[group('django')]
collectstatic: (manage "collectstatic --no-input")

[group('django')]
shell *options: migrate (manage "shell_plus --print-sql " + options)

[group('django')]
makemigrations *options: (manage "makemigrations " + options)

[group('django')]
migrate: makemigrations create-cache (manage "migrate")

[group('bs')]
[script('bash')]
runme *options: t django-superuser migrate create-cache ensure-skeleton-key
    set -euxo pipefail
    cd project
    trap "poetry run coverage html --rcfile={{ justfile_dir() }}/pyproject.toml --show-contexts && echo 'open {{ justfile_dir() }}/project/htmlcov/index.html'" EXIT
    poetry run coverage  run --rcfile={{ justfile_dir() }}/pyproject.toml --branch manage.py runserver 9000 {{ options }}

alias runserver := runme

curl *options: django-superuser migrate create-cache ensure-skeleton-key
    curl -v --cookie cook --cookie-jar cook "{{ options }}"

[script('bash')]
curl-login:
    set -euxo pipefail
    b64_blob=$(echo -n bob:. | base64)
    header="Authorization: Basic ${b64_blob}"
    curl --cookie cook --cookie-jar cook --header "${header}" http://localhost:9000/three-way-login/

create-cache: (manage "createcachetable")

# For production -- doesn't restart when a file changes.
[group('bs')]
[script('bash')]
daphne: test django-superuser migrate create-cache collectstatic ensure-skeleton-key
    set -euo pipefail
    cd project
    tput rmam                   # disables line wrapping
    trap "tput smam" EXIT       # re-enables line wrapping when this little bash script exits
    export -n DJANGO_SETTINGS_MODULE # let project/asgi.py determine if we're development, staging, production, or whatever
    set -x
    poetry run daphne                                                               \
      --verbosity                                                                   \
      1                                                                             \
      --bind                                                                        \
      0.0.0.0                                                                       \
      --port 9000 \
      --log-fmt="%(asctime)sZ  %(levelname)s %(filename)s %(funcName)s %(message)s" \
      project.asgi:application

alias createsuperuser := django-superuser
alias superuser := django-superuser

[group('django')]
django-superuser: all-but-django-prep migrate (manage "create_insecure_superuser")

# Run tests with --exitfirst and --failed-first
[group('bs')]
t *options: makemigrations mypy (test "--exitfirst --failed-first " + options)

# Draw a nice entity-relationship diagram
[group('django')]
graph: migrate
    cd project && poetry run python manage.py graph_models app | dot -Tsvg > $TMPDIR/graph.svg
    open $TMPDIR/graph.svg

# Run all the tests
[group('bs')]
[script('bash')]
test *options: makemigrations mypy
    set -euxo pipefail
    cd project

    pytest_args="--create-db {{ options }} -n 8"

    case "${PYINSTRUMENT:-}" in
    t*)
      pyinstrument_exe=$(poetry env info --path)/bin/pyinstrument
      poetry run coverage run --rcfile={{ justfile_dir() }}/pyproject.toml --branch ${pyinstrument_exe} -m pytest ${pytest_args}
    ;;
    *)
      pytest_exe=$(poetry env info --path)/bin/pytest
      poetry run coverage run --rcfile={{ justfile_dir() }}/pyproject.toml --branch ${pytest_exe} ${pytest_args}
    ;;
    esac

# Display coverage from a test run
[group('bs')]
[script('bash')]
cover: test
    set -euxo pipefail
    cd project
    poetry run coverage html --rcfile={{ justfile_dir() }}/pyproject.toml --show-contexts
    open htmlcov/index.html

# Nix the virtualenv and anything not checked in to git, but leave the database.
[script('bash')]
clean: die-if-poetry-active
    poetry env info --path | tee >((echo -n "poetry env: " ; cat) > /dev/tty) | xargs --no-run-if-empty rm -rf
    git clean -dx --interactive

# typical usage: just nuke ; docker volume prune --all --force ; just dcu
[group('docker')]
[script('bash')]
dcu *options: version-file orb poetry-install-no-dev ensure-skeleton-key
    set -euo pipefail

    export DJANGO_SECRET_KEY=$(cat "${DJANGO_SECRET_FILE}")
    export DJANGO_SKELETON_KEY=$(cat "${DJANGO_SKELETON_KEY_FILE}")
    tput rmam                   # disables line wrapping
    trap "tput smam" EXIT       # re-enables line wrapping when this little bash script exits
    set -x
    export GIT_VERSION="$(cat project/VERSION)"
    docker compose up --build {{ options }}

ensure_git_repo_clean:
    [[ -z "$(git status --porcelain)" ]]

ensure_branch_is_main:
    [[ "$(git symbolic-ref HEAD)" = "refs/heads/main" ]]

[group('docker')]
prod *options: ensure_branch_is_main ensure_git_repo_clean
    CADDY_HOSTNAME=bridge.offby1.info COMPOSE_PROFILES=prod DOCKER_CONTEXT=ls just dcu {{ options }} --detach
    COMPOSE_PROFILES=prod                                   DOCKER_CONTEXT=ls docker compose logs django --follow

[group('docker')]
hetz *options: ensure_git_repo_clean
    CADDY_HOSTNAME=beta.bridge.offby1.info COMPOSE_PROFILES=prod DOCKER_CONTEXT=hetz just dcu {{ options }} --detach
    COMPOSE_PROFILES=prod                                        DOCKER_CONTEXT=hetz docker compose logs django --follow

# Kill it all.  Kill it all, with fire.
nuke: clean docker-nuke
