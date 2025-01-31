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
GIT_SYMBOLIC_REF = "unknown"
for fn in ("VERSION", "GIT_SYMBOLIC_REF"):
    try:
        with open(BASE_DIR / fn) as inf:
            globals()[fn] = inf.read().rstrip()
    except FileNotFoundError as e:
        print(f"{e}; ignoring")

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
    "debug_toolbar",
    "django_extensions",
    "template_partials",
    "app",
]

FASTDEV_STRICT_IF = True

# This works because tailscale's "serve" and "funnel" commands set these headers for us.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True

EVENTSTREAM_STORAGE_CLASS = "django_eventstream.storage.DjangoModelStorage"

EVENTSTREAM_CHANNELMANAGER_CLASS = "app.channelmanager.MyChannelManager"


MIDDLEWARE = [
    "app.middleware.swallow_annoying_exception.SwallowAnnoyingExceptionMiddleware",
    "log_request_id.middleware.RequestIDMiddleware",
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

LOGIN_REDIRECT_URL = "app:player"

GITLAB_HOMEPAGE = "https://gitlab.com/offby1/bridge-server/"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "app.template.context_processors.stick_that_gitlab_link_in_there_daddy_O",
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
            "format": "{asctime} {levelname:5} request_id={request_id} {filename}({lineno}) {funcName} {message}",
            "datefmt": "%Y-%m-%dT%H:%M:%S%z",
            "style": "{",
        },
    },
    "filters": {
        "require_debug_true_or_environment_staging": {
            "()": "app.utils.log.RequireDebugTrueOrEnvironmentStaging",
        },
        "request_id": {"()": "log_request_id.filters.RequestIDFilter"},
    },
    "handlers": {
        "console": {
            "level": "DEBUG",
            "filters": ["require_debug_true_or_environment_staging", "request_id"],
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
    },
    "loggers": {
        "app": {
            "level": "DEBUG",
        },
        "bridge": {
            "handlers": ["console"],
            "level": "DEBUG",
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
        "urllib3.connectionpool": {
            "level": "INFO",
        },
    },
}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "bridge_django_cache",
    }
}
