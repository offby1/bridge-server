import contextlib
import os

import sentry_sdk

from .base_settings import *  # noqa
from .base_settings import ALLOWED_HOSTS, SENTRY_SDK_INIT_DEFAULTS


@contextlib.contextmanager
def temp_umask(new_umask):
    old_umask = os.umask(new_umask)
    try:
        yield
    finally:
        os.umask(old_umask)


SECRET_KEY_FILE = os.environ.get("DJANGO_SECRET_FILE")

if SECRET_KEY_FILE is not None:
    with open(SECRET_KEY_FILE) as inf:
        SECRET_KEY = inf.read()

DEBUG = False

ALLOWED_HOSTS.append("django")  # for when we're running as part of a docker-compose stack

sentry_sdk.init(**dict(SENTRY_SDK_INIT_DEFAULTS, environment="production"))  # type: ignore
