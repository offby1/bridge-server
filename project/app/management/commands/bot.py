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
        # TODO: don't impersonate a player if they are an actual human, trying to use this site!
        action = data.get("action")
        table = data.get("table")

        try:
            table = Table.objects.get(pk=table)
        except Table.DoesNotExist:
            return

        handrecord = table.current_handrecord

        if action == "just formed" or set(data.keys()) == {"table", "player", "call"}:
            player_to_impersonate = handrecord.player_who_may_call
            if player_to_impersonate is not None:
                player_to_impersonate = player_to_impersonate.libraryThing
                a = table.current_auction

                # Try not to pass, because it's more entertaining to make a call that keeps the auction alive.
                legal_calls = a.legal_calls()
                if len(legal_calls) > 1:
                    call = legal_calls[1]  # great bidding strategy, that
                else:
                    call = legal_calls[0]

                time.sleep(1)
                handrecord.add_call_from_player(player=player_to_impersonate, call=call)
                self.stdout.write(
                    f"Just impersonated {player_to_impersonate} at {table} and said {call} on their behalf",
                )
        else:
            self.stderr.write(f"No idea what to do with {data=}")

    @retrying.retry(wait_exponential_multiplier=1000, retry_on_exception=is_requests_error)
    def run_forever(self):
        while True:
            messages = SSEClient(
                "http://localhost:9000/events/all-tables/",
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
