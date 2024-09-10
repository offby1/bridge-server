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

    docker run -d \
    --name postgres \
    -e POSTGRES_PASSWORD=postgres \
    -v pg-data:/var/lib/postgresql/data \
    --publish 5432:5432 \
    postgres

[group('postgres')]
pg-stop:
    -docker stop postgres

[group('postgres')]
[private]
pg-create-db: pg-start
    @if ! docker exec postgres createdb --username=postgres -T template0 bridge ; then echo "$(tput setaf 2)'database already exists' is OK! ctfo$(tput sgr0)"; fi


orb:
    orb start

[script('bash')]
docker-nuke: orb
    set -euxo pipefail

    echo "Killing containers!"
    docker ps -aq | xargs --no-run-if-empty docker rm -f
    echo "Killing volumes!"
    docker volume prune --all --force
    echo "Removing plugins!"
    docker plugin ls --quiet | xargs --no-run-if-empty docker plugin rm
    echo "Done!"


[group('postgres')]
pg-data: orb
    docker volume create pg-data
