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

        common_prefix = (
            f"{request.META['REMOTE_ADDR']} {user=} {request.method}:{request.path_info}"
        )

        before = time.time()
        response = self.get_response(request)
        after = time.time()

        duration_ms = int(round((after - before) * 1000))

        logger.info(
            "%s ...",
            common_prefix,
        )

        response_prefix = common_prefix + f" => {response.status_code}"

        # The debug toolbar adds this header.
        if (server_timing := response.headers.get("Server-Timing")) is not None:
            for wat in server_timing.split(", "):
                name, duration, desc = wat.split(";")
                _, duration = duration.split("=")
                _, desc = desc.split("=")
                logger.info(
                    "%s [%s: %s]",
                    response_prefix,
                    desc,
                    duration,
                )

        logger.info(
            "%s ms=%d",
            response_prefix,
            duration_ms,
        )
        return response
