# Data is "visible" from Mac at ~/OrbStack/docker/volumes/pg-data/, even when the
# container is not running.

# What's the deal with e.g. `PGUSER` and `POSTGRES_USER`?

# The latter is for the postgresql docker image, and (along with `POSTGRES_PASSWORD`) creates an initial user (it
# defaults to `postgres`; the password has no default).  Without a valid password, I *think* the db won't even come up.
# `PGDATABASE`, `PGHOST`, `PGPORT` and/or `PGUSER` are all for psql and presumably other postgres clients.


alias start := pg-start

[group('postgres')]
[script('bash')]
pg-start: orb
    set -euxo pipefail

    docker compose up --wait postgres --detach

# Doesn't work on MacOS, at least when running inside an orbstack machine, since the *host*'s redis is listening on 6379, and thus
# - we cannot start our own process listening on that port, 'cuz EADDRINUSE; and
# - we don't need it anyway
[linux]
[script('bash')]
redis:
    set -euxo pipefail

    docker container restart redis 2> /dev/null && exit

    docker run --detach --name redis --publish 6379:6379 redis

[group('postgres')]
drop: pg-start
    docker exec --user postgres server-postgres-1 dropdb --if-exists bridge
    # If we don't nuke this volume, then the next time we bring up postgres it won't recreate the "bridge" database.
    docker compose down --volumes postgres
    just pg-start

[group('postgres')]
backup: pg-start
    docker compose exec --user postgres postgres pg_dump bridge
    @echo 'Now "just drop"' > /dev/stderr
    @echo '"just start"' > /dev/stderr
    @echo '"docker compose exec --user postgres --no-TTY postgres psql bridge < wherever-you-saved-it"' > /dev/stderr

alias stop := pg-stop

[group('postgres')]
pg-stop:
    docker compose down postgres

orb:
    if [ "{{os()}}" = "macos" ]; then orb start; else echo not mac I guess; fi

[script('bash')]
docker-nuke: orb
    set -euo pipefail

    echo "Killing containers!"
    docker ps -aq | xargs --no-run-if-empty docker rm -f
    # echo "Killing volumes!"
    echo Not doing docker volume prune --all --force
    echo "Removing plugins!"
    docker plugin ls --quiet | xargs --no-run-if-empty docker plugin rm
    echo "Done!"
