from .base_settings import *  # noqa
from .base_settings import SENTRY_SDK_INIT_DEFAULTS, TEMPLATES
import sentry_sdk

# https://docs.djangoproject.com/en/5.0/topics/templates/#django.template.backends.django.DjangoTemplates says
#   'debug': ... defaults to the value of the DEBUG setting.
# but that seems not to be the case, so we set it explicitly to avoid an exception from coverage
#   django_coverage_plugin.plugin.DjangoTemplatePluginException: Template debugging must be enabled in settings.
TEMPLATES[0]["OPTIONS"]["debug"] = True  # type: ignore
DEBUG = True
POKEY_BOT_BUTTONS = True

sentry_sdk.init(**dict(SENTRY_SDK_INIT_DEFAULTS, environment="development"))  # type: ignore
