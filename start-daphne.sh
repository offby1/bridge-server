#!/bin/bash

# wrapper script for [daemontools](https://cr.yp.to/daemontools/)
# Meant to run in our docker container, not e.g. your laptop

set -euxo pipefail

cd /bridge/project

export PGHOST=postgres
export PYTHONUNBUFFERED=t       # https://github.com/django/daphne/pull/520

exec poetry run  daphne                                                                         \
    --bind 0.0.0.0                                                                              \
    --port 9000                                                                                 \
    --proxy-headers                                                                             \
    --verbosity  0                                                                              \
    project.asgi:application
