import logging
import zoneinfo

from django.utils import timezone

logger = logging.getLogger(__name__)

# Work around https://github.com/adamcharnock/django-tz-detect/issues/80


# Similar to the middleware in the `tz_detect` package, but:
# - uses zoneinfo, which actually works; as opposed to pytz, which doesn't
# - simpler.  I suspect the stuff I got rid of isn't needed for modern Django and modern browsers.
class BetterTimezoneMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if tz := request.session.get("detected_tz"):
            if isinstance(tz, str):
                # ``request.timezone_active`` is used in the template tag
                # to detect if the timezone has been activated
                request.timezone_active = True

                zi = zoneinfo.ZoneInfo(tz)
                timezone.activate(zi)
            else:
                logger.warning(
                    'Don\'t know what to do with `session["detected_tz"]` %r since it is not a string',
                    tz,
                )

        else:
            timezone.deactivate()

        return self.get_response(request)
