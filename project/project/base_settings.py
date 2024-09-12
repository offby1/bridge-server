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

import sentry_sdk

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

VERSION = "unknown"
try:
    with open(BASE_DIR / "VERSION") as inf:
        VERSION = inf.read()
except FileNotFoundError:
    pass

APP_NAME = "info.offby1.bridge"

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.0/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY: str | None = "django-insecure-d)83erqvk0gay745i(^j_l37bg$+14&zgc5=pf5o*-3w%!h$92"

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
    "django_eventstream",
    "django.contrib.admin",
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

EVENTSTREAM_STORAGE_CLASS = "django_eventstream.storage.DjangoModelStorage"
EVENTSTREAM_CHANNELMANAGER_CLASS = "app.channelmanager.MyChannelManager"
EVENTSTREAM_REDIS = {
    "host": os.environ.get("REDIS_HOST", "localhost"),
    "port": 6379,
    "db": 0,
}

MIDDLEWARE = [
    "debug_toolbar.middleware.DebugToolbarMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

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

POKEY_BOT_BUTTONS = True


sentry_sdk.init(
    dsn="https://a18e83409c4ba3304ff35d0097313e7a@o4507936352501760.ingest.us.sentry.io/4507936354205696",
    # Set traces_sample_rate to 1.0 to capture 100%
    # of transactions for tracing.
    traces_sample_rate=1.0,
    # Set profiles_sample_rate to 1.0 to profile 100%
    # of sampled transactions.
    # We recommend adjusting this value in production.
    profiles_sample_rate=1.0,
)
