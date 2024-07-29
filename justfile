set unstable

export DJANGO_SETTINGS_MODULE := env("DJANGO_SETTINGS_MODULE", "bridge_server.settings")
export POETRY_VIRTUALENVS_IN_PROJECT := "false"

[private]
default:
    just --list

[group('virtualenv')]
poetry-install:
    poetry install

[group('django')]
[private]
all-but-django-prep: poetry-install

[group('django')]
[private]
manage *options: all-but-django-prep
    poetry run python manage.py {{ options }}

[group('django')]
makemigrations *options: (manage "makemigrations " + options)

[group('django')]
migrate *options: makemigrations (manage "migrate " + options)

[group('bs')]
runme *options: migrate (manage "runserver " + options)

[group('bs')]
test *options: makemigrations
    poetry run pytest --exitfirst --failed-first --create-db {{ options }}

#  Nix the virtualenv and anything not checked in to git.
clean:
    poetry env info --path | xargs --no-run-if-empty rm -rf
    git clean -dx --interactive --exclude='*.sqlite3'
