set unstable

export DJANGO_SETTINGS_MODULE := env("DJANGO_SETTINGS_MODULE", "project.dev_settings")
export PGDATA := env("PGDATA", home_dir() / "Library/Application Support/Postgres/var-14")
export POETRY_VIRTUALENVS_IN_PROJECT := "false"

[private]
default:
    just --list

[group('postgres')]
pg-create-cluster:
    [ -d "${PGDATA}" ] || initdb

[group('postgres')]
[private]
pg-start: pg-create-cluster
    @pg_ctl status || pg_ctl start --log=/tmp/postgresql.log || tail /tmp/postgresql.log

alias start := pg-start

[group('postgres')]
[private]
pg-stop: pg-create-cluster
    if pg_ctl status; then pg_ctl stop; fi

alias stop := pg-stop

[group('postgres')]
[private]
pg-create-db: pg-start
    if ! createdb -T template0 bridge ; then echo "$(tput setaf 2)'database already exists' is OK! ctfo$(tput sgr0)"; fi

[group('postgres')]
[private]
pg-overall-prep: pg-create-cluster pg-start pg-create-db

[group('postgres')]
drop: pg-start
    if ! dropdb  --force bridge; then echo "$(tput setaf 2)'database does not exist' is OK! ctfo$(tput sgr0)"; fi

[private]
[script('bash')]
die-if-poetry-active:
    if [[ -n "${POETRY_ACTIVE:-}" || -n "${VIRTUAL_ENV:-}" ]]
    then
      echo Hey man some environment variables suggest that a virtualenv is active
      env | sort | grep --extended "POETRY_ACTIVE|VIRTUAL_ENV"

      false
    fi

[group('virtualenv')]
poetry-install: die-if-poetry-active
    poetry install

mypy: poetry-install
    poetry run mypy . --exclude=/migrations/

[private]
version-file:
    git describe --always --dirty --tags > project/VERSION

[private]
pre-commit:
    -pre-commit install

[group('django')]
[private]
all-but-django-prep: version-file pre-commit poetry-install pg-overall-prep

[group('django')]
[private]
manage *options: all-but-django-prep
    cd project && poetry run python manage.py {{ options }}

[group('django')]
collectstatic: (manage "collectstatic --no-input")

[group('django')]
shell *options: migrate (manage "shell_plus --print-sql " + options)

[group('django')]
makemigrations *options: (manage "makemigrations " + options)

[group('django')]
migrate *options: makemigrations (manage "migrate " + options)

[group('bs')]
[script('bash')]
runme *options: test django-superuser migrate
    set -euxo pipefail
    cd project
    trap "poetry run coverage html --rcfile={{ justfile_dir() }}/pyproject.toml --show-contexts && echo 'open htmlcov/index.html'" EXIT
    poetry run coverage  run --rcfile={{ justfile_dir() }}/pyproject.toml --branch manage.py runserver 9000 {{ options }}

alias runserver := runme

# For production -- doesn't restart when a file changes.
[group('bs')]
[script('bash')]
daphne: test django-superuser migrate collectstatic
    set -euxo pipefail
    cd project
    tput rmam                   # disables line wrapping
    trap "tput smam" EXIT       # re-enables line wrapping when this little bash script exits
    export -n DJANGO_SETTINGS_MODULE
    poetry run daphne                                                               \
      --verbosity                                                                   \
      1                                                                             \
      --bind                                                                        \
      0.0.0.0                                                                       \
      --port 9000 \
      --log-fmt="%(asctime)sZ  %(levelname)s %(filename)s %(funcName)s %(message)s" \
      project.asgi:application

# Create a bunch of users and tables
[group('bs')]
pop: django-superuser migrate (manage "generate_fake_data --players=56")

# Run the little bids-and-plays bot
[group('bs')]
bot *options: migrate
    cd project && poetry run python manage.py bot {{ options }}

# Run many bots in parallel
[group('bs')]
[script('bash')]
botstorm: migrate
    set -euxo pipefail
    cd project
    for i in $(seq 15)
    do
       poetry run python manage.py bot --table=${i} &
    done
    wait

[group('django')]
[private]
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
    pytest_exe=$(poetry env info --path)/bin/pytest
    poetry run coverage run --rcfile={{ justfile_dir() }}/pyproject.toml --branch ${pytest_exe} --create-db {{ options }}

# Display coverage from a test run
[group('bs')]
[script('bash')]
cover: test
    set -euxo pipefail
    cd project
    poetry run coverage html --rcfile={{ justfile_dir() }}/pyproject.toml --show-contexts
    open htmlcov/index.html

#  Nix the virtualenv and anything not checked in to git, but leave the database.
[script('bash')]
clean: die-if-poetry-active
    poetry env info --path | tee >((echo -n "poetry env: " ; cat) > /dev/tty) | xargs --no-run-if-empty rm -rf
    git clean -dx --interactive --exclude='*.sqlite3'

# Kill it all.  Kill it all, with fire.
nuke: clean drop
