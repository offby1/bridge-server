# Data is "visible" from Mac at ~/OrbStack/docker/volumes/pg-data/, even when the
# container is not running.
# What's the deal with e.g. `PGUSER` and `POSTGRES_USER`?
# The latter is for the postgresql docker image, and (along with `POSTGRES_PASSWORD`) creates an initial user (it
# defaults to `postgres`; the password has no default).  Without a valid password, I *think* the db won't even come up.
# `PGDATABASE`, `PGHOST`, `PGPORT` and/or `PGUSER` are all for psql and presumably other postgres clients.

start: pg-start redis

redis: orb
    docker compose up --wait redis --detach

[group('postgres')]
[script('bash')]
pg-start: orb
    set -euxo pipefail

    docker compose up --wait postgres --detach

[private]
[script('bash')]
die-if-not-local-docker:
    set -euo pipefail

    case ${DOCKER_CONTEXT:-} in
        "orbstack"|"default")
            echo "DOCKER_CONTEXT is '$DOCKER_CONTEXT' so I guess it's OK to nuke everything."
        ;;
        *)
            echo "Not a great idea to drop a production database, eh what?"
            false
            ;;
    esac

[group('postgres')]
drop: die-if-not-local-docker pg-stop pg-start
    # If we don't nuke this volume, then the next time we bring up postgres it won't recreate the "bridge" database.
    docker compose down --volumes postgres
    docker compose down --volumes redis
    just pg-start redis

[group('postgres')]
backup: pg-start
    docker compose exec --user postgres postgres pg_dump bridge > {{ datetime_utc("%FT%T%z") }}.sql

[group('postgres')]
restore *options: drop pg-start
    docker compose exec --user postgres --no-TTY postgres psql bridge {{ options }}

stop: pg-stop
    docker compose down redis

[group('postgres')]
pg-stop: die-if-not-local-docker orb
    docker compose down postgres

[group('docker')]
[private]
dump-docker-context:
    @docker context inspect --format json | jq '.[].Endpoints.docker.Host'

orb:
    if [ "{{ os() }}" = "macos" ]; then orb start; else echo not mac I guess; fi
    just dump-docker-context

[script('bash')]
docker-nuke: die-if-not-local-docker orb
    set -euo pipefail

    echo "Killing containers!"
    docker ps -aq | xargs --no-run-if-empty docker rm -f

    echo "Killing postgres volume!"
    docker volume rm --force server_postgres_data

    echo "Removing plugins!"
    docker plugin ls --quiet | xargs --no-run-if-empty docker plugin rm

    echo "Done!"
