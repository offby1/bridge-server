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
    cd project && poetry run python manage.py {{ options }}

[group('django')]
shell *options: (manage "shell_plus --print-sql " + options)

[group('django')]
makemigrations *options: (manage "makemigrations " + options)

[group('django')]
migrate *options: makemigrations (manage "migrate " + options)

[group('bs')]
runme *options: test django-superuser migrate (manage "runserver " + options)

# Create a bunch of users and tables
[group('bs')]
pop *options: migrate (manage "generate_fake_data " + options)

[group('django')]
[private]
django-superuser: all-but-django-prep migrate
    if ! DJANGO_SUPERUSER_PASSWORD=admin poetry run python3 project/manage.py createsuperuser --no-input --username=$USER --email=eric.hanchrow@gmail.com;  then echo "$(tput setaf 2)'That username is already taken' is OK! ctfo$(tput sgr0)"; fi

[group('bs')]
test *options: makemigrations
    cd project && poetry run pytest --exitfirst --failed-first --create-db {{ options }}

# Delete the sqlite database.
[group('bs')]
drop:
    -rm -fv project/db.sqlite3

#  Nix the virtualenv and anything not checked in to git, but leave the database.
clean:
    poetry env info --path | xargs --no-run-if-empty rm -rf
    git clean -dx --interactive --exclude='*.sqlite3'
