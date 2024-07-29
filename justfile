set unstable

export DJANGO_SETTINGS_MODULE := env("DJANGO_SETTINGS_MODULE", "project.settings")
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
    poetry run python project/manage.py {{ options }}

[group('django')]
makemigrations *options: (manage "makemigrations " + options)

[group('django')]
migrate *options: makemigrations (manage "migrate " + options)

[group('bs')]
runme *options: django-superuser migrate (manage "runserver " + options)

[group('bs')]
loaddata *options: migrate (manage "loaddata " + options)

[group('django')]
[private]
django-superuser: all-but-django-prep migrate
    if ! DJANGO_SUPERUSER_PASSWORD=admin poetry run python3 project/manage.py createsuperuser --no-input --username=$USER --email=eric.hanchrow@gmail.com;  then echo "$(tput setaf 2)'That username is already taken' is OK! ctfo$(tput sgr0)"; fi

[group('bs')]
test *options: makemigrations
    poetry run pytest --exitfirst --failed-first --create-db {{ options }}

#  Nix the virtualenv and anything not checked in to git.
clean:
    poetry env info --path | xargs --no-run-if-empty rm -rf
    git clean -dx --interactive --exclude='*.sqlite3'
