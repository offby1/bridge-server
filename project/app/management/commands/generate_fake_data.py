import tqdm
from app.models import SEAT_CHOICES, Player, Seat, Table
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
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
            while Player.objects.count() < options["players"]:
                username = fake.unique.first_name().lower()
                django_user = User.objects.create_user(
                    username=username,
                    password=username,
                )

                p = Player.objects.create(user=django_user)
                progress_bar.update()

                # if there are no empty tables, create one
                # find a seat at the first empty table
                # update the player
                t = Table.objects.get_nonfull().first()
                if t is None:
                    t = Table.objects.create()

                p_by_d = t.players_by_direction()
                for d in SEAT_CHOICES.keys():
                    if d not in p_by_d:
                        Seat.objects.create(direction=d, player=p, table=t)
                        break

        # Now eject players from any non-full table, only so that we can have some warm bodies in the lobby.
        # Not sure if this makes any sense.
        t = Table.objects.get_nonfull().first()
        if t:
            for _, p in t.players_by_direction().items():
                s = p.seat
                s.player = None
                s.save()
            t.delete()

        self.stdout.write(f"{Player.objects.count()} players at {Table.objects.count()} tables.")
