import random

import django.db.utils
import retrying  # type: ignore
import tqdm
from app.models import Player, Table
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import IntegrityError
from faker import Faker


def is_retryable_db_error(e):
    return isinstance(
        e,
        (
            django.db.utils.OperationalError,
            django.db.utils.DatabaseError,
        ),
    ) and not isinstance(e, IntegrityError)


db_retry = retrying.retry(
    retry_on_exception=is_retryable_db_error,
    wait_exponential_multiplier=2,
    wait_jitter_max=1000,
)


canned_calls = [
    "Pass",
    "1NT",
    "Double",
    "Pass",
    "2♣",
    "Pass",
    "Pass",
    "3NT",
    "Double",
    "Redouble",
    "Pass",
    "Pass",
    "Pass",
    "Pass",
]


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument(
            "--players",
            default=14,
            type=int,
        )

    def generate_some_fake_calls_and_plays_at(self, table, this_tables_index):
        h = table.current_handrecord

        calls_prefix = canned_calls[0:this_tables_index]

        for c in calls_prefix:

            @db_retry
            def create_call():
                h.call_set.create(serialized=c)

            create_call()

    def handle(self, *args, **options):
        random.seed(0)  # TODO -- remove me when I'm done debugging

        # Use the same password for everybody, to speed things up :-)
        everybodys_password = make_password(".")

        fake = Faker()

        with tqdm.tqdm(desc="players", total=options["players"], unit="p") as progress_bar:
            while Player.objects.count() < options["players"]:
                # Make sure we always have "bob", because his name is easy to type, and to remember :-)
                if not Player.objects.exists():
                    username = "bob"
                else:
                    username = fake.unique.first_name().lower()

                @db_retry
                def create_player():
                    return Player.objects.create(
                        user=User.objects.create(
                            username=username,
                            password=everybodys_password,
                        ),
                    )

                try:
                    create_player()
                except IntegrityError:
                    continue

                progress_bar.update()

        # Now partner 'em up
        while True:
            single_players = Player.objects.filter(partner__isnull=True).all()[0:2]

            if len(single_players) < 2:
                break

            single_players[0].partner_with(single_players[1])

        # Now seat those players.
        while True:
            unseated_player_one = Player.objects.filter(
                partner__isnull=False, seat__isnull=True
            ).first()

            if not unseated_player_one:
                break

            # find another unseated partnership
            unseated_player_two = (
                Player.objects.exclude(
                    pk__in={unseated_player_one.pk, unseated_player_one.partner.pk}
                )
                .filter(partner__isnull=False, seat__isnull=True)
                .first()
            )

            if not unseated_player_two:
                break

            Table.objects.create_with_two_partnerships(
                unseated_player_one,
                unseated_player_two,
            )

        last_table = Table.objects.order_by("-pk").first()
        self.generate_some_fake_calls_and_plays_at(last_table, Table.objects.count() - 1)

        # Now create a couple of unseated players.
        count_before = Player.objects.count()
        while Player.objects.count() < count_before + 3:
            username = fake.unique.first_name().lower()

            @db_retry
            def create_player():
                return Player.objects.create(
                    user=User.objects.create(
                        username=username,
                        password=everybodys_password,
                    ),
                )

            try:
                create_player()
            except IntegrityError:
                continue

        self.stdout.write(f"{Player.objects.count()} players at {Table.objects.count()} tables.")

        # Now find some tables with complete auctions, and play a few cards.
        playable_tables = [t for t in Table.objects.all() if t.current_auction.found_contract]
        for t in tqdm.tqdm(
            playable_tables,
            desc="tables",
            unit="t",
        ):
            for _ in range(2):
                h = t.current_handrecord
                legal_cards = h.xscript.legal_cards()
                if legal_cards:
                    chosen_card = random.choice(legal_cards)

                    self.stdout.write(f"At {t}, playing {chosen_card} from {legal_cards}")
                    h.add_play_from_player(player=h.xscript.player, card=chosen_card)
