FROM python:3.13-slim-bullseye AS python
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

RUN apt -y update
RUN apt -y install git

ENV PYTHONUNBUFFERED=t

RUN adduser  --disabled-password bridge

COPY --chown=bridge:bridge server/uv.lock server/pyproject.toml /bridge/
WORKDIR /bridge
USER bridge
RUN ["uv", "sync", "--no-dev"]

FROM python:3.13-slim-bullseye

RUN adduser  --disabled-password bridge

COPY --chown=bridge:bridge --from=python /bin/uv /bin/uvx /bin/
COPY --chown=bridge:bridge --from=python /bridge/ /bridge/

COPY --chown=bridge:bridge /server/project /bridge/project/

# Note that someone -- typically docker-compose -- needs to have run "collectstatic" and "migrate" first
COPY --chown=bridge:bridge /server/start-daphne.sh /bridge/project

WORKDIR /bridge/project

USER bridge
CMD ["bash", "-c", "cd /bridge/project/ && uv run --no-dev python manage.py createcachetable && ./start-daphne.sh"]
