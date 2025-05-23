# Data is "visible" from Mac at ~/OrbStack/docker/volumes/pg-data/, even when the
# container is not running.
# What's the deal with e.g. `PGUSER` and `POSTGRES_USER`?
# The latter is for the postgresql docker image, and (along with `POSTGRES_PASSWORD`) creates an initial user (it
# defaults to `postgres`; the password has no default).  Without a valid password, I *think* the db won't even come up.
# `PGDATABASE`, `PGHOST`, `PGPORT` and/or `PGUSER` are all for psql and presumably other postgres clients.

start: pg-start

[group('postgres')]
[script('bash')]
pg-start: orb
    set -euxo pipefail

    docker compose up --wait postgres --detach

[group('postgres')]
drop: pg-stop pg-start
    docker exec --user postgres server-postgres-1 dropdb --if-exists bridge
    # If we don't nuke this volume, then the next time we bring up postgres it won't recreate the "bridge" database.
    docker compose down --volumes postgres
    just pg-start

[group('postgres')]
backup: pg-start
    docker compose exec --user postgres postgres pg_dump bridge > {{ datetime_utc("%FT%T%z") }}.sql

[group('postgres')]
restore *options: drop pg-start
    docker compose exec --user postgres --no-TTY postgres psql bridge {{ options }}

[group('postgres')]
grab-prod-backups:
    DOCKER_CONTEXT=ls just backup

alias stop := pg-stop

[group('postgres')]
pg-stop: orb
    docker compose down postgres

[group('docker')]
[private]
dump-docker-context:
    @docker context inspect --format json | jq '.[].Endpoints.docker.Host'

orb:
    if [ "{{ os() }}" = "macos" ]; then orb start; else echo not mac I guess; fi
    just dump-docker-context

[script('bash')]
docker-nuke: orb
    set -euo pipefail

    echo "Killing containers!"
    docker ps -aq | xargs --no-run-if-empty docker rm -f
    # echo "Killing volumes!"
    docker volume prune --all --force
    echo "Removing plugins!"
    docker plugin ls --quiet | xargs --no-run-if-empty docker plugin rm
    echo "Done!"
