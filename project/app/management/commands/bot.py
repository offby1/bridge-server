from __future__ import annotations

import contextlib
import json
import time
import typing

import requests
import retrying  # type: ignore
from app.models import AuctionException, Table
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

            if player_to_impersonate is None:
                self.stderr.write("player_to_impersonate is None??!")
                return

            if player_to_impersonate.is_human:
                self.stderr.write(
                    f"They tell me {player_to_impersonate} is human, so I will bow out",
                )
                return

            if player_to_impersonate.user.last_login is not None:
                self.stderr.write(
                    f"Human or not, {player_to_impersonate} has logged in, so I will bow out",
                )
                return

            player_to_impersonate = player_to_impersonate.libraryThing
            a = table.current_auction

            # Try not to pass, because it's more entertaining to make a call that keeps the auction alive.
            legal_calls = a.legal_calls()
            if len(legal_calls) > 1:
                call = legal_calls[1]  # I happen to know that legal_calls[0] is always Pass :-)
            else:
                call = legal_calls[0]

            time.sleep(1)
            try:
                handrecord.add_call_from_player(player=player_to_impersonate, call=call)
            except AuctionException as e:
                # The one time I saw this was when I clicked on a blue bidding box as soon as it appeared.  Then the
                # add_call_from_player call above discovered that the player_to_impersonate was out of turn.
                self.stderr.write(f"Uh-oh -- {e}")
            else:
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
        with contextlib.suppress(KeyboardInterrupt):
            self.run_forever()
