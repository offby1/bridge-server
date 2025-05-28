import logging
import time

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware:
    def __init__(self, get_response) -> None:
        self.get_response = get_response

    def __call__(self, request):
        before = time.time()
        response = self.get_response(request)
        after = time.time()
        duration_ms = int(round((after - before) * 1000))
        logger.info(
            "%s %s:%s => %s [%d ms]",
            request.META["REMOTE_ADDR"],
            request.method,
            request.path_info,
            response.status_code,
            duration_ms,
        )
        return response
