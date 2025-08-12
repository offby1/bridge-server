import os

from django.conf import settings


# Roughly, "is it safe to use hard-coded passwords, or trash the database, or create a fleet of killer bots"
def is_safe(stderr) -> bool:
    DJANGO_SETTINGS_MODULE = os.environ.get("DJANGO_SETTINGS_MODULE")
    DOCKER_CONTEXT = os.environ.get("DOCKER_CONTEXT")

    stderr.write(f"{settings.DEBUG=} {DOCKER_CONTEXT=} {DJANGO_SETTINGS_MODULE=}")

    if settings.DEBUG:
        return True

    return DOCKER_CONTEXT in {"default", "hetz-beta", "orbstack"}
