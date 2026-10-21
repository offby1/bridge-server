# The exact Python patch release, shared by both stages below.  The virtualenv that the
# builder creates records this version, and `uv run` deletes and recreates a virtualenv
# whose Python differs from the interpreter it finds -- which fails in the runtime
# stage, because that stage has no git to fetch our git dependencies.  With a floating
# tag like "3.14", Docker can use a stale local copy of one stage's base image and a
# fresh pull of the other's, and the two disagree.  A full version tag cannot drift.
# Bump this on purpose when a new patch release comes out.
ARG PYTHON_VERSION=3.14.9

# ---- Builder stage: full toolchain, used to compile endplay's DDS solver ----
#
# endplay publishes no cp314 wheel, and even where it must build from source its
# published sdist is unbuildable, so we consume a fork (see the bridge library's
# pyproject.toml). Building it compiles a C++ shared library, which needs a
# C/C++ toolchain + make. The full (non-slim) python image bundles those, plus
# git (needed by uv to fetch the git dependencies). cmake itself is supplied
# automatically by uv, via endplay's build-system requires.
FROM python:${PYTHON_VERSION}-bookworm AS builder
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

# Work around weird `fatal: could not read Username for 'https://github.com'` error
RUN git config --global http.version HTTP/1.1

RUN ["uv", "sync", "--no-dev"]

# ---- Runtime stage: slim image, no toolchain ----
#
# Same Debian release (bookworm) and Python version as the builder, so the
# virtualenv copied from the builder (including the self-contained libdds.so) is
# ABI-compatible and runs as-is.
FROM python:${PYTHON_VERSION}-slim-bookworm

RUN adduser  --disabled-password bridge

COPY --chown=bridge:bridge --from=builder /bin/uv /bin/uvx /bin/
COPY --chown=bridge:bridge --from=builder /bridge/ /bridge/

COPY --chown=bridge:bridge /server/project /bridge/project/

# Note that someone -- typically docker-compose -- needs to have run "collectstatic" and "migrate" first
COPY --chown=bridge:bridge /server/start-daphne.sh /bridge/project

WORKDIR /bridge/project

USER bridge
CMD ["bash", "-c", "cd /bridge/project/ && uv run --no-dev python manage.py createcachetable && ./start-daphne.sh"]
