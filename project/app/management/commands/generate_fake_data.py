import more_itertools
import tqdm
from app.models import Player, Table
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from faker import Faker


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument(
            "--players",
            default=13,
            type=int,
        )
        parser.add_argument(
            "--tables",
            default=3,
            type=int,
        )

    def handle(self, *args, **options):
        fake = Faker()

        with tqdm.tqdm(total=options["players"]) as progress_bar:
            while Player.objects.count() < options["players"]:
                username = fake.unique.first_name().lower()
                django_user = User.objects.create_user(
                    username=username,
                    password=username,
                )

                Player.objects.create(user=django_user)
                progress_bar.update()

        with tqdm.tqdm(total=options["tables"]) as progress_bar:
            for compass_points in more_itertools.chunked(Player.objects.all(), 4):
                if len(compass_points) < 4:
                    break

                kwargs = dict(zip(["north", "east", "south", "west"], compass_points))
                print(f"{kwargs=}")
                Table.objects.create(**kwargs)
                progress_bar.update()

        self.stdout.write(f"{Player.objects.count()} players at {Table.objects.count()} tables.")
