import platform

from django.conf import settings
from django.http import HttpRequest


def add_various_bits_of_handy_info(request: HttpRequest) -> dict[str, str]:
    return {
        "gitlab_homepage": settings.GITLAB_HOMEPAGE,
        "GIT_SYMBOLIC_REF": settings.GIT_SYMBOLIC_REF,
        "VERSION": settings.VERSION,
        "DEPLOYMENT_ENVIRONMENT": settings.DEPLOYMENT_ENVIRONMENT,
        "PLATFORM": platform.platform(),
    }
