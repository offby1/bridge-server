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

FROM python AS node-exporter

RUN apt-get update && apt-get install --no-install-recommends -y \
  curl \
  && apt-get purge -y --auto-remove -o APT::AutoRemove::RecommendsImportant=false \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /service/node_exporter/
RUN curl --location -O https://github.com/prometheus/node_exporter/releases/download/v1.9.1/node_exporter-1.9.1.linux-amd64.tar.gz
RUN tar zxf node_exporter-1.9.1.linux-amd64.tar.gz
RUN mv node_exporter-1.9.1.linux-amd64/node_exporter run
RUN rm -rf node_exporter-1.9.1.linux-amd64.tar.gz node_exporter-1.9.1.linux-amd64/

FROM python AS app


RUN apt-get update && apt-get install --no-install-recommends -y \
  daemontools \
  && apt-get purge -y --auto-remove -o APT::AutoRemove::RecommendsImportant=false \
  && rm -rf /var/lib/apt/lists/*

COPY --from=poetry-install-django /bridge/ /bridge/
COPY /server/project /bridge/project/

COPY --from=poetry-install-apibot /api-bot/ /api-bot/
COPY /api-bot/*.py /api-bot/

COPY --from=node-exporter /service/node_exporter/ /service/node_exporter/

# Note that someone -- typically docker-compose -- needs to have run "collectstatic" and "migrate" first
COPY /server/start-daphne.sh /service/daphne/run

WORKDIR /bridge/project

CMD ["bash", "-c", "cd /bridge/project/ && poetry run python manage.py createcachetable && poetry run python manage.py synchronize_bot_states && (cd /service && svscan) "]
