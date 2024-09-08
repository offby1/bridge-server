import collections
import json
import time
import typing

import django.db.utils
import requests
import retrying  # type: ignore
from app.models import AuctionException, Table
from django.core.management.base import BaseCommand
from sseclient import SSEClient  # type: ignore


class Command(BaseCommand):
    def dispatch(self, *, data: dict[str, typing.Any]) -> None:
        action = data.get("action")

        try:
            table = Table.objects.get(pk=data.get("table"))
        except Table.DoesNotExist:
            self.stderr.write(f"Warning: table {table} does not exist")
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

            # Hopefully if we were using Postgres instead of sqlite, these wouldn't be necessary.
            @retrying.retry(
                retry_on_exception=(
                    django.db.utils.OperationalError,
                    django.db.utils.DatabaseError,
                ),
                wait_exponential_multiplier=10,
                wait_jitter_max=1000,
            )
            def add_call():
                handrecord.add_call_from_player(player=player_to_impersonate, call=call)

            try:
                add_call()
            except AuctionException as e:
                # The one time I saw this was when I clicked on a blue bidding box as soon as it appeared.  Then the
                # add_call_from_player call above discovered that the player_to_impersonate was out of turn.
                self.stderr.write(f"Uh-oh -- {e}")
            else:
                self.stdout.write(
                    f"Just impersonated {player_to_impersonate} at {table} and said {call} on their behalf",
                )

            now = time.time()
            sleep_until = self.last_action_timestamps_by_table_id[table.pk] + 1
            self.last_action_timestamps_by_table_id[table.pk] = now

            if sleep_until - now > 0:
                time.sleep(sleep_until - now)

        else:
            self.stderr.write(f"No idea what to do with {data=}")

    @retrying.retry(
        retry_on_exception=(requests.exceptions.HTTPError, requests.exceptions.ConnectionError),
        wait_exponential_multiplier=1000,
    )
    def run_forever(self):
        while True:
            messages = SSEClient(
                "http://localhost:9000/events/all-tables/",
            )
            for msg in messages:
                if msg.event != "keep-alive":
                    if msg.data:
                        data = json.loads(msg.data)
                        self.dispatch(data=data)
                    else:
                        self.stdout.write(f"message with no data: {vars(msg)=}")

            self.stderr.write("Consumed all messages; starting over")
            time.sleep(1)

    def handle(self, *args, **options):
        self.last_action_timestamps_by_table_id = collections.defaultdict(lambda: 0)
        try:
            self.run_forever()
        except KeyboardInterrupt:
            pass
