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


DEBUG = False

ALLOWED_HOSTS.append("django")  # for when we're running as part of a docker-compose stack

HOST_HOSTNAME = os.getenv("HOST_HOSTNAME", "unknown-host")
print(f"prod_settings: {HOST_HOSTNAME=}")

# "development": running on my laptop without docker
# "staging": running on my laptop with docker
# "production": running on my EC2 box or some other cloud server, with docker
DEPLOYMENT_ENVIRONMENT = "production" if HOST_HOSTNAME == "ip-10-0-0-174" else "staging"

sentry_sdk.init(  # type: ignore
    dsn="https://a18e83409c4ba3304ff35d0097313e7a@o4507936352501760.ingest.us.sentry.io/4507936354205696",
    # Set traces_sample_rate to 1.0 to capture 100%
    # of transactions for tracing.
    environment=DEPLOYMENT_ENVIRONMENT,
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
