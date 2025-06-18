import cProfile
import logging
import pstats
import sys
import time

import django.db.utils

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware:
    def __init__(self, get_response) -> None:
        self.get_response = get_response

    def __call__(self, request):
        if (
            request.path_info == "/metrics"
        ):  # prometheus hits this every 15 seconds; such logs are not useful
            return self.get_response(request)

        try:
            user = getattr(getattr(request, "user", None), "username", None)
        except django.db.utils.OperationalError:
            logger.exception("That's it, we're outta here")
            sys.exit(1)

        common_prefix = (
            f"{request.META['REMOTE_ADDR']} {user=} {request.method}:{request.path_info}"
        )

        pr = cProfile.Profile()
        enabled = False
        before = time.time()

        try:
            pr.enable()
        except ValueError as e:
            logger.warning("%s", e)
        else:
            enabled = True

        try:
            response = self.get_response(request)
        finally:
            pr.disable()

        after = time.time()
        duration_ms = int(round((after - before) * 1000))

        if enabled and duration_ms > 1_000:
            output_filename = f"/tmp/{duration_ms:04}ms"
            if (request_id := getattr(request, "id", None)) is not None:
                output_filename += f"-{request_id}"
            pr.dump_stats(output_filename)


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
