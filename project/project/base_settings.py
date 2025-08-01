"""Django settings for project project.

Generated by 'django-admin startproject' using Django 5.0.7.

For more information on this file, see
https://docs.djangoproject.com/en/5.0/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/5.0/ref/settings/
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
import sys
from typing import Any

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

VERSION = "unknown"
GIT_SYMBOLIC_REF = "unknown"
for fn in ("VERSION", "GIT_SYMBOLIC_REF"):
    try:
        with open(BASE_DIR / fn) as inf:
            globals()[fn] = inf.read().rstrip()
    except FileNotFoundError as e:
        print(f"{e}; ignoring", file=sys.stderr)

del fn

APP_NAME = "info.offby1.bridge"

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.0/howto/deployment/checklist/


def from_env_var_file(env_varname: str, fallback_filename: str) -> str | None:
    filename = os.environ.get(
        env_varname,
        fallback_filename,
    )

    if filename is None:
        return None

    with open(filename) as inf:
        return inf.read()


# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = from_env_var_file(
    "DJANGO_SECRET_FILE",
    # This default works on my laptop, and nowhere else; it's here just to make it easier for me to run Visual Studio Code.
    "/Users/not-workme/Library/Application Support/info.offby1.bridge/django_secret_key",
)

API_SKELETON_KEY = from_env_var_file(
    "DJANGO_SKELETON_KEY_FILE",
    "/Users/not-workme/Library/Application Support/info.offby1.bridge/django_skeleton_key",
)
if API_SKELETON_KEY is not None:
    API_SKELETON_KEY = API_SKELETON_KEY.rstrip()

ALLOWED_HOSTS = [
    ".offby1.info",
    ".orb.local",
    ".tail571dc2.ts.net",  # tailscale!
    "127.0.0.1",
    "django",  # for prometheus
    "localhost",
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
    "django_tables2",
    "debug_toolbar",
    "django_extensions",
    "django_prometheus",
    "template_partials",
    "tz_detect",
    "app",
]

FASTDEV_STRICT_IF = True

# This works because tailscale's "serve" and "funnel" commands set these headers for us.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True

REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
EVENTSTREAM_REDIS = {
    "host": REDIS_HOST,
    "port": 6379,
    "db": 0,
}

EVENTSTREAM_CHANNELMANAGER_CLASS = "app.channelmanager.MyChannelManager"


MIDDLEWARE = [
    "django_prometheus.middleware.PrometheusBeforeMiddleware",
    "app.middleware.swallow_annoying_exception.SwallowAnnoyingExceptionMiddleware",
    "log_request_id.middleware.RequestIDMiddleware",
    "app.middleware.add_request_id.AddRequestIdToSQLConnectionMiddleware",
    "app.middleware.add_git_commit_hash.AddVersionHeaderMiddleware",
    "debug_toolbar.middleware.DebugToolbarMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.admindocs.middleware.XViewMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "app.middleware.simple_access_log.RequestLoggingMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_prometheus.middleware.PrometheusAfterMiddleware",
    "app.middleware.better_tz_detect.BetterTimezoneMiddleware",
]
LOG_REQUEST_ID_HEADER = "HTTP_X_REQUEST_ID"
REQUEST_ID_RESPONSE_HEADER = "X-Request-Id"
GENERATE_REQUEST_ID_IF_NOT_IN_HEADER = True

STORAGES = {"staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"}}

INTERNAL_IPS = [
    "127.0.0.1",
]

ROOT_URLCONF = "project.urls"

LOGIN_REDIRECT_URL = "app:player"

GITLAB_HOMEPAGE = "https://gitlab.com/offby1/bridge-server/"

DJANGO_TABLES2_TEMPLATE = "django_tables2/bootstrap5-responsive.html"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "app.template.context_processors.add_various_bits_of_handy_info",
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
        "ENGINE": "django_prometheus.db.backends.postgresql",
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


class MuffleObserverLogs(logging.Filter):
    def filter(self, record):
        if getattr(record, "filename", None) == "_observer.py":
            return False

        return True


LOGGING: dict[str, Any] = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            # https://docs.python.org/3.12/library/logging.html#logrecord-attributes
            "datefmt": "%Y-%m-%dT%H:%M:%S%z",
            "format": "{asctime} {levelname:5} pid={process} thread={threadName} request_id={request_id} {filename}({lineno}) {funcName} {message}",
            "style": "{",
        },
    },
    "filters": {
        "muffle_observer_logs": {"()": MuffleObserverLogs},
        "request_id": {"()": "log_request_id.filters.RequestIDFilter"},
    },
    "handlers": {
        "console": {
            "level": "DEBUG",
            "filters": ["request_id", "muffle_observer_logs"],
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
        # "file": {
        #     "level": "DEBUG",
        #     "class": "logging.FileHandler",
        #     "filename": "/tmp/django.log",
        # },
    },
    "root": {
        "handlers": [
            "console",
            # "file"
        ],
    },
    "loggers": {
        "app": {
            "level": "DEBUG",
        },
        "asyncio": {
            "level": "INFO",
        },
        "daphne.http_protocol": {
            "level": "INFO",
        },
        "django.channels.server": {
            "level": "INFO",
        },
        "django.core.cache": {
            "level": "DEBUG",
        },
        "django_eventstream.views": {
            "level": "WARNING",
        },
        "faker.factory": {
            "level": "CRITICAL",  # please shut up please please please
        },
        "urllib3.connectionpool": {
            "level": "INFO",
        },
    },
}

CACHES = {
    "default": {
        # TODO -- there might be a prometheus-flavored redis cache; if so, I should use that.
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": f"redis://{REDIS_HOST}:6379",
        # "BACKEND": "django.core.cache.backends.dummy.DummyCache",
    }
}
