import json
import time
import typing

import requests
import retrying  # type: ignore
from app.models import Table
from django.core.management.base import BaseCommand
from sseclient import SSEClient  # type: ignore


def is_requests_error(exception):
    return isinstance(
        exception,
        (requests.exceptions.HTTPError, requests.exceptions.ConnectionError),
    )


class Command(BaseCommand):
    def dispatch(self, data: dict[str, typing.Any]) -> None:
        # TODO -- somehow ignore events that result from actions that *we* just took :-) Lest we loop endlessly.
        action = data.get("action")
        table = data.get("table")

        if action == "just formed":
            table = Table.objects.get(pk=table)
            handrecord = table.current_handrecord
            player = handrecord.player_who_may_call
            if player is not None:
                self.stdout.write(
                    f"Pretend I impersonated {player} at {table} and made a call on their behalf",
                )

    @retrying.retry(wait_exponential_multiplier=1000, retry_on_exception=is_requests_error)
    def run_forever(self):
        while True:
            messages = SSEClient(
                "http://localhost:8000/events/all-tables/",
            )
            for msg in messages:
                if msg.event != "keep-alive":
                    if msg.data:
                        data = json.loads(msg.data)
                        self.dispatch(data)
                    else:
                        self.stdout.write(f"message with no data: {vars(msg)=}")

            self.stderr.write("Consumed all messages; starting over")
            time.sleep(1)

    def handle(self, *args, **options):
        try:
            self.run_forever()
        except KeyboardInterrupt:
            pass
