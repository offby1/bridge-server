"""
Test-specific Django settings that enable static file serving.

This configuration allows Playwright tests to load CSS/JS without running collectstatic.
"""

import os

from .base_settings import *  # noqa: F403

# Deployment environment marker for templates
DEPLOYMENT_ENVIRONMENT = "test"

# Override database settings for tests to prevent connection issues
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "HOST": os.environ.get("PGHOST", "localhost"),
        "NAME": "bridge",
        "PASSWORD": os.environ.get("PGPASS", "postgres"),
        "USER": os.environ.get("PGUSER", "postgres"),
        # Disable persistent connections for tests
        "CONN_MAX_AGE": 0,
        # Configure test database to allow forceful drop
        "TEST": {
            "NAME": "test_bridge",
        },
    },
}

# Use WhiteNoise but with a simpler storage backend for tests
# This allows serving static files directly from app directories without collectstatic
STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",  # No manifest needed
    }
}

# For tests, we want to serve static files from app directories
# WhiteNoise will handle this when DEBUG=True
DEBUG = True

# Disable some security features that interfere with test server
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_SSL_REDIRECT = False
SECURE_HSTS_SECONDS = 0

# Use in-memory cache for faster tests
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}
