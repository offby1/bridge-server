from __future__ import annotations

import collections
import contextlib
import json
import random
import time
import typing

import django.db.utils
import requests
import retrying  # type: ignore
from app.models import AuctionException, Table
from bridge.contract import Contract
from django.core.management.base import BaseCommand
from sseclient import SSEClient  # type: ignore


class Command(BaseCommand):
    def make_a_groovy_call(self, *, handrecord):
        table = handrecord.table
        player_to_impersonate = handrecord.player_who_may_call

        if player_to_impersonate is None:
            self.stderr.write("player_to_impersonate is None -- auction must be over.")
            return

        if player_to_impersonate.is_human:
            self.stderr.write(
                f"They tell me {player_to_impersonate} is human, so I will bow out",
            )
            # return

        if player_to_impersonate.user.last_login is not None:
            self.stderr.write(
                f"Human or not, {player_to_impersonate} has logged in, so I will bow out",
            )
            # return

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

    def make_a_groovy_play(self, *, handrecord):
        if not isinstance(handrecord.auction.status, Contract):
            return

        table = handrecord.table

        seat_to_impersonate = table.next_seat_to_play

        legal_cards = handrecord.xscript.legal_cards()
        if not legal_cards:
            self.stderr.write(f"No legal cards at {seat_to_impersonate}? The hand must be over.")
            return

        chosen_card = random.choice(legal_cards)

        p = handrecord.add_play_from_player(player=handrecord.xscript.player, card=chosen_card)
        self.stdout.write(f"At {table}, played {p} from {legal_cards}")

    def maybe_sleep(self, *, table):
        now = time.time()
        sleep_until = self.last_action_timestamps_by_table_id[table.pk] + 1
        self.last_action_timestamps_by_table_id[table.pk] = now

        if sleep_until - now > 0:
            time.sleep(sleep_until - now)

    def dispatch(self, *, data: dict[str, typing.Any]) -> None:
        action = data.get("action")

        try:
            table = Table.objects.get(pk=data.get("table"))
        except Table.DoesNotExist:
            self.stderr.write(f"In {data}, table {data.get('table')=} does not exist")
            return

        handrecord = table.current_handrecord

        if action == "just formed" or set(data.keys()) == {"table", "player", "call"}:
            self.make_a_groovy_call(handrecord=handrecord)
            self.maybe_sleep(table=table)

        elif set(data.keys()) == {"table", "contract"} or set(data.keys()) == {
            "table",
            "player",
            "card",
        }:
            self.make_a_groovy_play(handrecord=handrecord)
            self.maybe_sleep(table=table)
        elif set(data.keys()) == {"table", "direction", "action"}:
            self.stderr.write(f"I wonder if someone at {data=} wanted to tell me something")
            self.make_a_groovy_call(handrecord=handrecord)
            self.make_a_groovy_play(handrecord=handrecord)
            self.maybe_sleep(table=table)
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

        with contextlib.suppress(KeyboardInterrupt):
            self.run_forever()
