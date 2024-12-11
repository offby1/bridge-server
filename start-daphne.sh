#!/bin/bash

# wrapper script for [daemontools](https://cr.yp.to/daemontools/)

set -euxo pipefail

cd /bridge/project

export PGHOST=postgres

poetry run  daphne                                                                              \
    --verbosity  3                                                                              \
    --bind 0.0.0.0                                                                              \
    --port 9000                                                                                 \
    project.asgi:application                                                                    \
    --log-fmt="%(asctime)sZ %(levelname)s %(name)s %(filename)s %(funcName)s %(message)s"
