import bridge
import tqdm
from app.models import Player, Seat, Table
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db.models import Count
from faker import Faker


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument(
            "--players",
            default=14,
            type=int,
        )
        parser.add_argument(
            "--tables",
            default=3,
            type=int,
        )

    def handle(self, *args, **options):
        fake = Faker()

        with tqdm.tqdm(desc="players", total=options["players"], unit="p") as progress_bar:
            unseated_players = []
            while Player.objects.count() < options["players"]:
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

                Table.objects.create_with_two_partnerships(
                    unseated_players[0],
                    unseated_players[2],
                )
                unseated_players = []

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
