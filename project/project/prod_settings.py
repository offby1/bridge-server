import os


from .base_settings import *  # noqa
from .base_settings import LOGGING

DEBUG = False

# "development": running on my laptop without docker
# "staging": running on my laptop with docker
# "production": running on my EC2 box or some other cloud server, with docker
DEPLOYMENT_ENVIRONMENT = "production" if os.getenv("COMPOSE_PROFILES") == "prod" else "staging"

if DEPLOYMENT_ENVIRONMENT == "production":
    LOGGING["handlers"]["console"]["level"] = "INFO"
