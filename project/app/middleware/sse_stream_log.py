# Diagnostic instrumentation for the SSE connection leak described in TROUBLE.md.
#
# Chrome allows only six concurrent HTTP/1.1 connections per origin. Each
# text/event-stream response holds one for as long as it lives, so a stream that
# flaps -- dying and being re-dialed by ReconnectingEventSource without its socket
# being released -- consumes the budget until the browser can no longer send
# anything at all. The access log can't show this: it logs when the
# StreamingHttpResponse object is created, which is roughly instant, and never
# reports when the stream actually ends.
#
# This middleware logs the open and the close of every stream, along with why it
# closed and how many remain open, so the next occurrence explains itself.

import itertools
import logging
import threading
import time

from django.http import StreamingHttpResponse

logger = logging.getLogger(__name__)

_stream_ids = itertools.count(1)
_open_streams: set[int] = set()
_lock = threading.Lock()


def _opened(stream_id: int, path: str) -> None:
    with _lock:
        _open_streams.add(stream_id)
        count = len(_open_streams)
    logger.info("SSE stream #%d open: %s (%d now open)", stream_id, path, count)


def _closed(stream_id: int, path: str, reason: str, started: float) -> None:
    with _lock:
        _open_streams.discard(stream_id)
        count = len(_open_streams)
    logger.info(
        "SSE stream #%d close: %s after %.1fs (%s; %d still open)",
        stream_id,
        path,
        time.monotonic() - started,
        reason,
        count,
    )


class SSEStreamLoggingMiddleware:
    """Log the lifetime of every text/event-stream response."""

    def __init__(self, get_response) -> None:
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if not isinstance(response, StreamingHttpResponse):
            return response
        if not response.get("Content-Type", "").startswith("text/event-stream"):
            return response

        stream_id = next(_stream_ids)
        path = request.get_full_path()
        started = time.monotonic()
        _opened(stream_id, path)

        # GeneratorExit means the server closed the generator without exhausting it,
        # which is what a client disconnect looks like from in here.
        if response.is_async:
            inner_async = response.streaming_content

            async def awrapper():
                reason = "exhausted"
                try:
                    async for chunk in inner_async:
                        yield chunk
                except GeneratorExit:
                    reason = "client disconnected"
                    raise
                except BaseException as e:
                    reason = f"{type(e).__name__}: {e}"
                    raise
                finally:
                    _closed(stream_id, path, reason, started)

            response.streaming_content = awrapper()
        else:
            inner_sync = response.streaming_content

            def wrapper():
                reason = "exhausted"
                try:
                    yield from inner_sync
                except GeneratorExit:
                    reason = "client disconnected"
                    raise
                except BaseException as e:
                    reason = f"{type(e).__name__}: {e}"
                    raise
                finally:
                    _closed(stream_id, path, reason, started)

            response.streaming_content = wrapper()

        return response
