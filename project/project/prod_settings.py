import contextlib
import os

import django.core.management.utils
import platformdirs

from .base_settings import *  # noqa
from .base_settings import APP_NAME  # redundant, but removes some complaints from emacs


@contextlib.contextmanager
def temp_umask(new_umask):
    old_umask = os.umask(new_umask)
    try:
        yield
    finally:
        os.umask(old_umask)


secret_key_path = (
    platformdirs.site_data_path(appname=APP_NAME, ensure_exists=True) / "django_secret_key"
)
if not secret_key_path.is_file():
    with temp_umask(0o77):
        with open(secret_key_path, "w") as outf:
            outf.write(django.core.management.utils.get_random_secret_key())
    print(f"Created secret key at {secret_key_path}")

with open(secret_key_path) as inf:
    SECRET_KEY = inf.read()
    print(f"read SECRET_KEY from {secret_key_path=}")

DEBUG = False
