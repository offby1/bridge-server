import logging
import time

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware:
    def __init__(self, get_response) -> None:
        self.get_response = get_response

    def __call__(self, request):
        if (
            request.path_info == "/metrics"
        ):  # prometheus hits this every 15 seconds; such logs are not useful
            return self.get_response(request)

        user = getattr(getattr(request, "user", None), "username", None)

        before = time.time()
        response = self.get_response(request)
        after = time.time()
        duration_ms = int(round((after - before) * 1000))

        # Pass each item as a separate parameter, so that Sentry can "see" them as individual items
        logger.info(
            "%s %s %s:%s => %s ms=%d",
            request.META["REMOTE_ADDR"],
            f"{user=}",
            request.method,
            request.path_info,
            response.status_code,
            duration_ms,
        )
        return response
