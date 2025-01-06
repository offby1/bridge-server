import logging

from .base_settings import *  # noqa
from .base_settings import TEMPLATES

# https://docs.djangoproject.com/en/5.0/topics/templates/#django.template.backends.django.DjangoTemplates says
#   'debug': ... defaults to the value of the DEBUG setting.
# but that seems not to be the case, so we set it explicitly to avoid an exception from coverage
#   django_coverage_plugin.plugin.DjangoTemplatePluginException: Template debugging must be enabled in settings.
TEMPLATES[0]["OPTIONS"]["debug"] = True  # type: ignore
DEBUG = True

LOGGING["loggers"]["django.channels.server"]["level"] = logging.WARNING  # type: ignore
LOGGING["loggers"]["django_eventstream"] = {"handlers": ["console"], "level": "DEBUG"}  # type: ignore
# See notes in prod_settings
DEPLOYMENT_ENVIRONMENT = "development"
