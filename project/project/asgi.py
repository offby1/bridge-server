"""ASGI config for project project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.0/howto/deployment/asgi/
"""

import os
import sys

from django.conf import settings
from django.core.asgi import get_asgi_application

try:
    import pyroscope  # type: ignore [import-untyped,import-not-found]
except ModuleNotFoundError:
    pass
else:
    pyroscope.configure(
        application_name="bridge",
        server_address=f"http://{os.environ.get('PYROSCOPE_HOST', 'localhost')}:4040",
    )

print()
print(f"{os.environ["DJANGO_SETTINGS_MODULE"]=}")
print(f"{settings.DEPLOYMENT_ENVIRONMENT=} {settings.SECURE_SSL_REDIRECT=}")
print(f"{settings.VERSION=}")
print(f"{settings.GIT_SYMBOLIC_REF=}")
sys.stdout.flush()

application = get_asgi_application()
