# ---- Builder stage: full toolchain, used to compile endplay's DDS solver ----
#
# endplay publishes no cp314 wheel, and even where it must build from source its
# published sdist is unbuildable, so we consume a fork (see the bridge library's
# pyproject.toml). Building it compiles a C++ shared library, which needs a
# C/C++ toolchain + make. The full (non-slim) python image bundles those, plus
# git (needed by uv to fetch the git dependencies). cmake itself is supplied
# automatically by uv, via endplay's build-system requires.
FROM python:3.13-bullseye AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV PYTHONUNBUFFERED=t

# Statically link libstdc++ and libgcc into endplay's compiled libdds.so, so at
# runtime it depends only on glibc -- which the slim runtime image already has.
# This keeps the runtime image's package surface unchanged (no libstdc++6 to
# install there). CMake seeds its linker flags from the LDFLAGS environment
# variable on a fresh configure and applies them to shared-library links, so
# setting it here is enough; no patch to endplay is required.
ENV LDFLAGS="-static-libgcc -static-libstdc++"

RUN adduser --disabled-password bridge

COPY --chown=bridge:bridge server/uv.lock server/pyproject.toml /bridge/
WORKDIR /bridge
USER bridge
RUN ["uv", "sync", "--no-dev"]

# ---- Runtime stage: slim image, no toolchain ----
#
# Same Debian release (bullseye) and Python version as the builder, so the
# virtualenv copied from the builder (including the self-contained libdds.so) is
# ABI-compatible and runs as-is.
FROM python:3.13-slim-bullseye

RUN adduser  --disabled-password bridge

COPY --chown=bridge:bridge --from=builder /bin/uv /bin/uvx /bin/
COPY --chown=bridge:bridge --from=builder /bridge/ /bridge/

COPY --chown=bridge:bridge /server/project /bridge/project/

# Note that someone -- typically docker-compose -- needs to have run "collectstatic" and "migrate" first
COPY --chown=bridge:bridge /server/start-daphne.sh /bridge/project

WORKDIR /bridge/project

USER bridge
CMD ["bash", "-c", "cd /bridge/project/ && uv run --no-dev python manage.py createcachetable && ./start-daphne.sh"]
