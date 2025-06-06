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

        log_message_prefix = f"{request.META['REMOTE_ADDR']} {request.method}:{request.path_info} => {response.status_code}"

        # The debug toolbar adds this header.
        if (server_timing := response.headers.get("Server-Timing")) is not None:
            for wat in server_timing.split(", "):
                name, duration, desc = wat.split(";")
                _, duration = duration.split("=")
                _, desc = desc.split("=")
                logger.info(
                    "%s [%s: %s]",
                    log_message_prefix,
                    desc,
                    duration,
                )

        logger.info(
            "%s ms=%d",
            log_message_prefix,
            duration_ms,
        )
        return response
