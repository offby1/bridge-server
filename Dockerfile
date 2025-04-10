FROM python:3.13-slim-bullseye AS python
ENV POETRY_VIRTUALENVS_IN_PROJECT=true \
  POETRY_NO_INTERACTION=1

RUN pip install -U pip setuptools; pip install poetry

FROM python AS poetry-install-django

COPY server/poetry.lock server/pyproject.toml /bridge/
WORKDIR /bridge
RUN poetry install --without=dev

FROM python AS poetry-install-apibot

COPY api-bot/poetry.lock api-bot/pyproject.toml /api-bot/
WORKDIR /api-bot
RUN poetry install

FROM python AS app

RUN apt-get update && apt-get install --no-install-recommends -y \
  daemontools \
  && apt-get purge -y --auto-remove -o APT::AutoRemove::RecommendsImportant=false \
  && rm -rf /var/lib/apt/lists/*

COPY --from=poetry-install-django /bridge/ /bridge/
COPY /server/project /bridge/project/

COPY --from=poetry-install-apibot /api-bot/ /api-bot/
COPY /api-bot/*.py /api-bot/

# Note that someone -- typically docker-compose -- needs to have run "collectstatic" and "migrate" first
COPY /server/start-daphne.sh /service/daphne/run

WORKDIR /bridge/project

CMD ["bash", "-c", "cd /bridge/project/ && poetry run python manage.py createcachetable && (cd /service && svscan) && poetry run python manage.py synchronize_bot_states"]
