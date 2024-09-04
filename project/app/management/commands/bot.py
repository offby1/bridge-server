import requests
import retrying
from django.core.management.base import BaseCommand
from sseclient import SSEClient


def is_requests_error(exception):
    return isinstance(
        exception,
        (requests.exceptions.HTTPError, requests.exceptions.ConnectionError),
    )


class Command(BaseCommand):
    @retrying.retry(wait_exponential_multiplier=1000, retry_on_exception=is_requests_error)
    def run_forever(self):
        while True:
            messages = SSEClient(
                "http://localhost:8000/events/table/1/",
            )
            for msg in messages:
                if msg.event != "keep-alive":
                    self.stdout.write(f"Ooh ooh Mr Kotter {vars(msg)=}")

    def handle(self, *args, **options):
        try:
            self.run_forever()
        except KeyboardInterrupt:
            pass
