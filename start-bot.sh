#!/bin/bash

# wrapper script for [daemontools](https://cr.yp.to/daemontools/)
# Meant to run in our docker container, not e.g. your laptop

set -euxo pipefail

cd /bridge/project

export PYTHONUNBUFFERED=t       # https://github.com/django/daphne/pull/520

exec poetry run python manage.py cheating_bot
