set unstable

export DJANGO_SETTINGS_MODULE := env("DJANGO_SETTINGS_MODULE", "project.settings")
export POETRY_VIRTUALENVS_IN_PROJECT := "false"

[private]
default:
    just --list

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

[group('django')]
[private]
all-but-django-prep: poetry-install

[group('django')]
[private]
manage *options: all-but-django-prep
    cd project && poetry run python manage.py {{ options }}

[group('django')]
collectstatic *options: (manage "collectstatic " + options)

[group('django')]
shell *options: migrate (manage "shell_plus --print-sql " + options)

[group('django')]
makemigrations *options: (manage "makemigrations " + options)

[group('django')]
migrate *options: makemigrations (manage "migrate " + options)

[group('bs')]
runme *options: test django-superuser migrate
    cd project && poetry run daphne --verbosity 3 --bind 0.0.0.0 {{ options }} project.asgi:application

# Create a bunch of users and tables
[group('bs')]
pop *options: django-superuser migrate (manage "generate_fake_data " + options)

[group('django')]
[private]
django-superuser: all-but-django-prep migrate (manage "create_insecure_superuser")

# Run tests with --exitfirst and --failed-first
[group('bs')]
t *options: makemigrations (test "--exitfirst --failed-first " + options)

# Run all the tests
[group('bs')]
[script('bash')]
test *options: makemigrations
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

# Delete the sqlite database.
[group('bs')]
drop:
    -rm -fv project/db.sqlite3

#  Nix the virtualenv and anything not checked in to git, but leave the database.
[script('bash')]
clean: die-if-poetry-active
    poetry env info --path | tee >((echo -n "poetry env: " ; cat) > /dev/tty) | xargs --no-run-if-empty rm -rf
    git clean -dx --interactive --exclude='*.sqlite3'

# Kill it all.  Kill it all, with fire.
nuke: clean drop
