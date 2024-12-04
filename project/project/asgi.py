"""ASGI config for project project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.0/howto/deployment/asgi/
"""

import os
import sys

from django.conf import settings
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "project.prod_settings")
print(f'{os.environ["DJANGO_SETTINGS_MODULE"]=}')
print(f"{settings.DEPLOYMENT_ENVIRONMENT=} {settings.SECURE_SSL_REDIRECT=}")
print(f"{settings.VERSION=}")
sys.stdout.flush()

application = get_asgi_application()
