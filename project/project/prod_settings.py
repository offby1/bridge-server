import logging
import os

import sentry_sdk
from sentry_sdk.integrations.logging import LoggingIntegration

from .base_settings import *  # noqa
from .base_settings import LOGGING, VERSION

DEBUG = False

# "development": running on my laptop without docker
# "staging": running on my laptop with docker
# "production": running on my EC2 box or some other cloud server, with docker
DEPLOYMENT_ENVIRONMENT = (
    "production" if "prod" in os.getenv("COMPOSE_PROFILES", "").split(",") else "staging"
)
SECURE_SSL_REDIRECT = True

# Prometheus scrapes django:9000/metrics directly (not through Caddy), so the request carries no
# X-Forwarded-Proto header; SECURE_SSL_REDIRECT would 301 it to https://django:9000, which daphne's
# plain-HTTP port can't complete (the scrape then dies with "context deadline exceeded").  Exempt the
# metrics endpoint from the redirect so the internal scrape works over HTTP.
#
# ai_bot (app/management/commands/ai_bot.py) hits the same wall: it plays synthetic seats
# purely through the public bot API (app/reference_client.py), but -- like Prometheus --
# talks straight to http://django:9000 (BRIDGE_BASE_URL in docker-compose.yaml), not through
# Caddy, so it too gets redirected into the same dead end. Exempt the specific bot-API paths
# it calls: /login/, /serialized/hand/<pk>/, /call/, /play/.
#
# This looks like it's weakening protection for exactly the endpoints (login credentials!)
# that most need it, but it isn't, because of where these requests can come from:
#   - django:9000 is bound to 127.0.0.1 only (docker-compose.yaml's `ports:` for the django
#     service), so it is unreachable from outside the host -- not from the internet, not
#     even from the LAN or Tailscale. Only the host itself or another container on the
#     compose network can ever reach it directly.
#   - Every real, internet-facing request already goes through Caddy, which terminates TLS
#     and auto-redirects any plain-HTTP request to HTTPS *before* Django ever sees it
#     (docker-compose-caddy.yaml publishes 80 and 443, and caddy/Caddyfile never disables
#     Caddy's default auto_https). SECURE_SSL_REDIRECT plus HSTS below is Django's own
#     defense-in-depth on top of that, not the only thing standing between an attacker and
#     a plaintext login.
# So this exemption only ever applies to callers already inside that trust boundary -- the
# same one /metrics above relies on -- never to a real external client.
SECURE_REDIRECT_EXEMPT = [r"^metrics$", r"^login/$", r"^serialized/hand/", r"^call/$", r"^play/$"]

if DEPLOYMENT_ENVIRONMENT == "production":
    LOGGING["handlers"]["console"]["level"] = "INFO"

# https://docs.sentry.io/platforms/python/integrations/django/
sentry_sdk.init(  # type: ignore
    dsn="https://a18e83409c4ba3304ff35d0097313e7a@o4507936352501760.ingest.us.sentry.io/4507936354205696",
    # Add data like request headers and IP for users;
    # see https://docs.sentry.io/platforms/python/data-management/data-collected/ for more info
    send_default_pii=True,
    environment=DEPLOYMENT_ENVIRONMENT,
    # Set traces_sample_rate to 1.0 to capture 100%
    # of transactions for tracing.
    traces_sample_rate=1.0,
    # To collect profiles for all profile sessions,
    # set `profile_session_sample_rate` to 1.0.
    profile_session_sample_rate=1.0,
    # Profiles will be automatically collected while
    # there is an active span.
    profile_lifecycle="trace",
    release=VERSION,
    _experiments={
        "enable_logs": True,
    },
    integrations=[
        LoggingIntegration(sentry_logs_level=logging.INFO),
    ],
)
