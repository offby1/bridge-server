import asyncio.exceptions
import logging

from django.http import HttpResponse
from django.utils.html import escape

logger = logging.getLogger(__name__)


# This turns a baffling 30-line stack trace into a merely puzzling warning.


class SwallowAnnoyingExceptionMiddleware:
    def __init__(self, get_response) -> None:
        self.get_response = get_response

    def __call__(self, request):
        try:
            return self.get_response(request)
        except asyncio.exceptions.CancelledError as e:
            msg = f"Ignoring {e=} because I don't know what else to do"
            logger.warning("%s", msg)
            return HttpResponse(escape(msg))
