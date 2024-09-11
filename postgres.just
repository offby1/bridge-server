# Data is "visible" from Mac at ~/OrbStack/docker/volumes/pg-data/, even when the
# container is not running.

# What's the deal with e.g. `PGUSER` and `POSTGRES_USER`?

# The latter is for the postgresql docker image, and (along with `POSTGRES_PASSWORD`) creates an initial user (it
# defaults to `postgres`; the password has no default).  Without a valid password, I *think* the db won't even come up.
# `PGDATABASE`, `PGHOST`, `PGPORT` and/or `PGUSER` are all for psql and presumably other postgres clients.


[group('postgres')]
[script('bash')]
pg-start: orb pg-data
    set -euxo pipefail

    docker container restart postgres 2> /dev/null && exit

    docker run --detach \
    --name postgres \
    --env POSTGRES_PASSWORD=postgres \
    --volume pg-data:/var/lib/postgresql/data \
    --publish 5432:5432 \
    postgres

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
pg-stop:
    -docker stop postgres

[group('postgres')]
[private]
pg-create-db: pg-start
    until docker exec postgres pg_isready --username=postgres; do sleep 1; date; done
    if ! docker exec postgres createdb --username=postgres -T template0 bridge ; then echo "$(tput setaf 2)'database already exists' is OK! ctfo$(tput sgr0)"; fi


orb:
    if [ "{{os()}}" = "macos" ]; then orb start; else echo not mac I guess; fi

[script('bash')]
docker-nuke: orb
    set -euxo pipefail

    echo "Killing containers!"
    docker ps -aq | xargs --no-run-if-empty docker rm -f
    # echo "Killing volumes!"
    echo Not doing docker volume prune --all --force
    echo "Removing plugins!"
    docker plugin ls --quiet | xargs --no-run-if-empty docker plugin rm
    echo "Done!"


[group('postgres')]
pg-data: orb
    docker volume create pg-data
