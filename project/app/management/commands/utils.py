import os

from django.conf import settings


def is_safe(stderr) -> bool:
    DJANGO_SETTINGS_MODULE = os.environ.get("DJANGO_SETTINGS_MODULE")
    DOCKER_CONTEXT = os.environ.get("DOCKER_CONTEXT")

    stderr.write(f"{settings.DEBUG=} {DOCKER_CONTEXT=} {DJANGO_SETTINGS_MODULE=}")

    if settings.DEBUG:
        return True

    return DOCKER_CONTEXT in {"hetz-beta", "orbstack"}
