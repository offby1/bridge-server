import logging

from django.conf import settings


class RequireDebugTrueOrEnvironmentStaging(logging.Filter):
    def filter(self, record):
        return settings.DEBUG or settings.DEPLOYMENT_ENVIRONMENT == "staging"
