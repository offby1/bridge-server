FROM python:3.13-slim-bullseye AS python
ENV POETRY_VIRTUALENVS_IN_PROJECT=true \
  POETRY_NO_INTERACTION=1

RUN pip install -U pip setuptools; pip install poetry

FROM python AS poetry-install

COPY poetry.lock pyproject.toml /bridge/
WORKDIR /bridge
RUN poetry install

FROM python AS app

RUN apt-get update && apt-get install --no-install-recommends -y \
  libpq5 \
  && apt-get purge -y --auto-remove -o APT::AutoRemove::RecommendsImportant=false \
  && rm -rf /var/lib/apt/lists/*

COPY --from=poetry-install /bridge/ /bridge/
COPY /project /bridge/project/
WORKDIR /bridge/project
ENV PGHOST=postgres

# Note that someone -- typically docker-compose -- needs to have run "collectstatic" and "migrate" first
CMD ["bash", "-c", "poetry run daphne --verbosity 3 --bind 0.0.0.0 --port 9000 project.asgi:application --log-fmt=\"%(asctime)sZ %(levelname)s %(name)s %(filename)s %(funcName)s %(message)s\""]
