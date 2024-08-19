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
                django_user = User.objects.create_user(
                    username=username,
                    password=username,
                )

                p = Player.objects.create(user=django_user)
                progress_bar.update()
                unseated_players.append(p)

                if len(unseated_players) < 2:
                    continue

                # if there are no tables with two open seats, create one
                t = Table.objects.annotate(num_seats=Count("seat")).filter(num_seats__lt=3).first()
                if t is None:
                    t = Table.objects.create()

                # find a seat at the first empty table
                this_tables_players_by_direction = t.players_by_direction()
                for seat in bridge.seat.Seat:
                    if seat.value not in this_tables_players_by_direction:
                        unseated_players[0].partner_with(unseated_players[1])
                        Seat.objects.create(
                            direction=seat.value,
                            player=unseated_players[0],
                            table=t,
                        )
                        Seat.objects.create(
                            direction=seat.partner().value,
                            player=unseated_players[1],
                            table=t,
                        )
                        unseated_players = []
                        break

        # Now create a couple of unseated players.
        count_before = Player.objects.count()
        while Player.objects.count() < count_before + 3:
            username = fake.unique.first_name().lower()
            django_user = User.objects.create_user(
                username=username,
                password=username,
            )

            Player.objects.create(user=django_user)

        self.stdout.write(f"{Player.objects.count()} players at {Table.objects.count()} tables.")
