FROM python:3.12-slim-bullseye AS python
ENV POETRY_VIRTUALENVS_IN_PROJECT=true \
  POETRY_NO_INTERACTION=1

RUN pip install -U pip setuptools; pip install poetry

FROM python AS poetry-install

COPY poetry.lock pyproject.toml /bridge/
WORKDIR /bridge
RUN poetry install

FROM python AS app
COPY --from=poetry-install /bridge/ /bridge/

RUN apt-get update && apt-get install --no-install-recommends -y \
  libpq5 \
  && apt-get purge -y --auto-remove -o APT::AutoRemove::RecommendsImportant=false \
  && rm -rf /var/lib/apt/lists/*

COPY /project /bridge/project/
WORKDIR /bridge/project
ENV PGHOST=postgres
ENV REDIS_HOST=redis

CMD ["bash", "-c", "poetry run python manage.py collectstatic --no-input && poetry run python manage.py migrate && poetry run daphne --verbosity 3 --bind 0.0.0.0 --port 9000 project.asgi:application"]
