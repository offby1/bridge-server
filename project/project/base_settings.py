"""Django settings for project project.

Generated by 'django-admin startproject' using Django 5.0.7.

For more information on this file, see
https://docs.djangoproject.com/en/5.0/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/5.0/ref/settings/
"""

from __future__ import annotations

import os
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

VERSION = "unknown"
try:
    with open(BASE_DIR / "VERSION") as inf:
        VERSION = inf.read().rstrip()
except FileNotFoundError:
    pass

APP_NAME = "info.offby1.bridge"

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.0/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY: str
DJANGO_SECRET_FILE = os.environ.get(
    "DJANGO_SECRET_FILE",
    # This default works on my laptop, and nowhere else; it's here just to make it easier for me to run Visual Studio Code.
    "/Users/not-workme/Library/Application Support/info.offby1.bridge/django_secret_key",
)

if DJANGO_SECRET_FILE is not None:
    with open(DJANGO_SECRET_FILE) as inf:
        SECRET_KEY = inf.read()

ALLOWED_HOSTS = [
    ".orb.local",
    ".tail571dc2.ts.net",  # tailscale!
    "127.0.0.1",
    "192.168.4.39",  # laptop at home
    "localhost",
    "offby1.info",
]
CSRF_TRUSTED_ORIGINS = [
    "https://teensy-info.tail571dc2.ts.net",
    "https://erics-work-macbook-pro.tail571dc2.ts.net",
]

# Application definition

INSTALLED_APPS = [
    "daphne",
    "django_fastdev",
    "django_eventstream",
    "django.contrib.admin",
    "django.contrib.admindocs",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "debug_toolbar",
    "django_extensions",
    "rest_framework",
    "template_partials",
    "app",
]

FASTDEV_STRICT_IF = True

REST_FRAMEWORK = {
    # Use Django's standard `django.contrib.auth` permissions,
    # or allow read-only access for unauthenticated users.
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.DjangoModelPermissionsOrAnonReadOnly"
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.LimitOffsetPagination",
    "PAGE_SIZE": 100,
}

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True
SECURE_SSL_REDIRECT = True
SECURE_REDIRECT_EXEMPT = [
    r"^events/"
]  # for the bot when it's running on the same host and connecting to localhost

EVENTSTREAM_STORAGE_CLASS = "django_eventstream.storage.DjangoModelStorage"

EVENTSTREAM_CHANNELMANAGER_CLASS = "app.channelmanager.MyChannelManager"
EVENTSTREAM_REDIS = {
    "host": os.environ.get("REDIS_HOST", "localhost"),
    "port": 6379,
    "db": 0,
}

MIDDLEWARE = [
    "app.middleware.add_git_commit_hash.AddVersionHeaderMiddleware",
    "debug_toolbar.middleware.DebugToolbarMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.admindocs.middleware.XViewMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

STORAGES = {"staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"}}

INTERNAL_IPS = [
    "127.0.0.1",
]

ROOT_URLCONF = "project.urls"

LOGIN_REDIRECT_URL = "app:home"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "app.template.context_processors.stick_that_version_in_there_daddy_O",
                "app.template.context_processors.stick_deployment_environment_in_there_daddy_O",
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

ASGI_APPLICATION = "project.asgi.application"
WSGI_APPLICATION = "project.wsgi.application"


# Database
# https://docs.djangoproject.com/en/5.0/ref/settings/#databases

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "HOST": os.environ.get("PGHOST", "localhost"),
        "NAME": "bridge",
        "PASSWORD": os.environ.get("PGPASS", "postgres"),
        "USER": os.environ.get("PGUSER", "postgres"),
    },
}
# Internationalization
# https://docs.djangoproject.com/en/5.0/topics/i18n/

LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.0/howto/static-files/

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "static_root"

# Default primary key field type
# https://docs.djangoproject.com/en/5.0/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            # https://docs.python.org/3.12/library/logging.html#logrecord-attributes
            "format": "{asctime} {levelname:5} {filename}({lineno}) {funcName} {message}",
            "datefmt": "%Y-%m-%dT%H:%M:%S%z",
            "style": "{",
        },
    },
    "filters": {
        "require_debug_true_or_environment_staging": {
            "()": "app.utils.log.RequireDebugTrueOrEnvironmentStaging",
        },
    },
    "handlers": {
        "console": {
            "level": "DEBUG",
            "filters": ["require_debug_true_or_environment_staging"],
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "loggers": {
        "app": {
            "handlers": ["console"],
            "level": "DEBUG",
        },
        "daphne.http_protocol": {
            "level": "INFO",
        },
        "django": {
            "handlers": ["console"],
            "propagate": True,
        },
        "django.channels.server": {
            "handlers": ["console"],
            "level": "INFO",
        },
        "django_eventstream.views": {
            "level": "WARNING",
        },
        "urllib3.connectionpool": {
            "level": "INFO",
        },
    },
}
