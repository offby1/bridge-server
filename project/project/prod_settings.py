import contextlib
import os

import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration

from .base_settings import *  # noqa
from .base_settings import ALLOWED_HOSTS, VERSION


@contextlib.contextmanager
def temp_umask(new_umask):
    old_umask = os.umask(new_umask)
    try:
        yield
    finally:
        os.umask(old_umask)


SECRET_KEY_FILE = os.environ.get("DJANGO_SECRET_FILE")

if SECRET_KEY_FILE is not None:
    with open(SECRET_KEY_FILE) as inf:
        SECRET_KEY = inf.read()

DEBUG = False

ALLOWED_HOSTS.append("django")  # for when we're running as part of a docker-compose stack

HOST_HOSTNAME = os.getenv("HOST_HOSTNAME", "unknown-host")
sentry_sdk.init(  # type: ignore
    dsn="https://a18e83409c4ba3304ff35d0097313e7a@o4507936352501760.ingest.us.sentry.io/4507936354205696",
    # Set traces_sample_rate to 1.0 to capture 100%
    # of transactions for tracing.
    environment="staging" if HOST_HOSTNAME.startswith("Erics-Work-MacBook-Pro") else "production",
    traces_sample_rate=1.0,
    # Set profiles_sample_rate to 1.0 to profile 100%
    # of sampled transactions.
    # We recommend adjusting this value in production.
    profiles_sample_rate=1.0,
    integrations=[
        DjangoIntegration(
            middleware_spans=False,
            signals_spans=False,
        ),
    ],
    release=VERSION,
)
