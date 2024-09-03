import random

import tqdm
from app.models import Player, Table
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from faker import Faker

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
            h.call_set.create(serialized=c)

    def handle(self, *args, **options):
        random.seed(0)  # TODO -- remove me when I'm done debugging
        fake = Faker()

        with tqdm.tqdm(desc="players", total=options["players"], unit="p") as progress_bar:
            unseated_players = []
            while Player.objects.count() < options["players"]:
                # Make sure we always have "bob", because his name is easy to type, and to remember :-)
                if not Player.objects.exists():
                    username = "bob"
                else:
                    username = fake.unique.first_name().lower()

                try:
                    p = Player.objects.create(
                        user=User.objects.create_user(
                            username=username,
                            password=username,
                        ),
                    )
                except Exception as e:
                    self.stderr.write(f"Hmm, {e}")
                    continue

                progress_bar.update()
                unseated_players.append(p)

                if len(unseated_players) < 4:
                    continue

                unseated_players[0].partner_with(unseated_players[1])
                unseated_players[2].partner_with(unseated_players[3])

                t = Table.objects.create_with_two_partnerships(
                    unseated_players[0],
                    unseated_players[2],
                )
                unseated_players = []

                self.generate_some_fake_calls_and_plays_at(t, Table.objects.count() - 1)

        # Now create a couple of unseated players.
        count_before = Player.objects.count()
        while Player.objects.count() < count_before + 3:
            username = fake.unique.first_name().lower()
            try:
                django_user = User.objects.create_user(
                    username=username,
                    password=username,
                )
            except Exception as e:
                self.stderr.write(f"Hmm, {e}")
                continue

            Player.objects.create(user=django_user)

        self.stdout.write(f"{Player.objects.count()} players at {Table.objects.count()} tables.")
