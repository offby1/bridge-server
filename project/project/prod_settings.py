import os

from .base_settings import *  # noqa
from .base_settings import ALLOWED_HOSTS, LOGGING, init_sentry_for_environment

DEBUG = False

ALLOWED_HOSTS.append("django")  # for when we're running as part of a docker-compose stack

# "development": running on my laptop without docker
# "staging": running on my laptop with docker
# "production": running on my EC2 box or some other cloud server, with docker
DEPLOYMENT_ENVIRONMENT = "production" if os.getenv("COMPOSE_PROFILES") == "prod" else "staging"

init_sentry_for_environment(environment=DEPLOYMENT_ENVIRONMENT)

if DEPLOYMENT_ENVIRONMENT == "production":
    LOGGING["handlers"]["console"]["level"] = "INFO"
