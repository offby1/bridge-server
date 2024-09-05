import json
import pprint
import time

import requests
import retrying  # type: ignore
from django.core.management.base import BaseCommand
from sseclient import SSEClient  # type: ignore


def is_requests_error(exception):
    return isinstance(
        exception,
        (requests.exceptions.HTTPError, requests.exceptions.ConnectionError),
    )


class Command(BaseCommand):
    @retrying.retry(wait_exponential_multiplier=1000, retry_on_exception=is_requests_error)
    def run_forever(self):
        while True:
            # Wait for a message that says either a new table has formed, or someone at an existing table has made a
            # call.

            # Figure out who's next to call.

            # Perhaps skip 'em if we can tell they're a human.

            # Grab their django User or Player instance, and call whatever the "call-post" view would call.

            messages = SSEClient(
                "http://localhost:8000/events/all-tables/",
            )
            for msg in messages:
                if msg.event != "keep-alive":
                    if msg.data:
                        formatted = pprint.pformat(json.loads(msg.data), compact=True)
                        self.stdout.write(formatted)
                    else:
                        self.stdout.write(f"Ooh ooh Mr Kotter {vars(msg)=}")

            self.stderr.write("Consumed all messages; starting over")
            time.sleep(1)

    def handle(self, *args, **options):
        try:
            self.run_forever()
        except KeyboardInterrupt:
            pass
