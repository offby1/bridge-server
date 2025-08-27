FROM python:3.13-slim-bullseye AS python
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

RUN apt -y update
RUN apt -y install git

ENV PYTHONUNBUFFERED=t

FROM python AS uv-install-django

COPY server/uv.lock server/pyproject.toml /bridge/
WORKDIR /bridge
RUN ["uv", "sync", "--no-dev"]

FROM python:3.13-slim-bullseye
RUN adduser --disabled-password bridge

COPY --from=uv-install-django /bin/uv /bin/uvx /bin/
COPY --from=uv-install-django /bridge/ /bridge/

COPY /server/project /bridge/project/

# Note that someone -- typically docker-compose -- needs to have run "collectstatic" and "migrate" first
COPY /server/start-daphne.sh /bridge/project

RUN chown -R bridge:bridge /bridge

WORKDIR /bridge/project

CMD ["bash", "-c", "cd /bridge/project/ && uv run --no-dev python manage.py createcachetable && ./start-daphne.sh"]
