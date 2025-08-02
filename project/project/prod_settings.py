import logging
import os

import sentry_sdk
from sentry_sdk.integrations.logging import LoggingIntegration

from .base_settings import *  # noqa
from .base_settings import LOGGING, VERSION

DEBUG = False

# "development": running on my laptop without docker
# "staging": running on my laptop with docker
# "production": running on my EC2 box or some other cloud server, with docker
DEPLOYMENT_ENVIRONMENT = "production" if os.getenv("COMPOSE_PROFILES") == "prod" else "staging"

if DEPLOYMENT_ENVIRONMENT == "production":
    LOGGING["handlers"]["console"]["level"] = "INFO"

# https://docs.sentry.io/platforms/python/integrations/django/
sentry_sdk.init(  # type: ignore
    dsn="https://a18e83409c4ba3304ff35d0097313e7a@o4507936352501760.ingest.us.sentry.io/4507936354205696",
    # Add data like request headers and IP for users;
    # see https://docs.sentry.io/platforms/python/data-management/data-collected/ for more info
    send_default_pii=True,
    environment=DEPLOYMENT_ENVIRONMENT,
    # Set traces_sample_rate to 1.0 to capture 100%
    # of transactions for tracing.
    traces_sample_rate=1.0,
    # To collect profiles for all profile sessions,
    # set `profile_session_sample_rate` to 1.0.
    profile_session_sample_rate=1.0,
    # Profiles will be automatically collected while
    # there is an active span.
    profile_lifecycle="trace",
    release=VERSION,
    _experiments={
        "enable_logs": True,
    },
    integrations=[
        LoggingIntegration(sentry_logs_level=logging.INFO),
    ],
)
