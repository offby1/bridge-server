FROM python:3.13-slim-bullseye AS python
ENV POETRY_VIRTUALENVS_IN_PROJECT=true \
  POETRY_NO_INTERACTION=1 \
  PYTHONUNBUFFERED=t

RUN pip install -U pip setuptools; pip install poetry

FROM python AS poetry-install-django

COPY server/poetry.lock server/pyproject.toml /bridge/
WORKDIR /bridge
RUN poetry install --without=dev

FROM python AS app

COPY --from=poetry-install-django /bridge/ /bridge/
COPY /server/project /bridge/project/

# Note that someone -- typically docker-compose -- needs to have run "collectstatic" and "migrate" first
COPY /server/start-daphne.sh /bridge/project

WORKDIR /bridge/project

CMD ["bash", "-c", "cd /bridge/project/ && poetry run python manage.py createcachetable && ./start-daphne.sh"]
