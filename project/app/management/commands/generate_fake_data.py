import tqdm
from app.models import Player, Seat, Table
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db.utils import IntegrityError
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
                try:
                    username = fake.first_name().lower()
                    django_user = User.objects.create_user(
                        username=username,
                        password=username,
                    )
                except IntegrityError:
                    continue
                Player.objects.create(user=django_user)
                progress_bar.update()

        for _ in range(options["tables"]):
            t = Table.objects.create(name=f"{Table.objects.count()}")
            Seat.create_for_table(t)

        while True:
            not_full_table = Table.non_full_table()
            if not_full_table is None:
                break
            unseated_player = Player.objects.filter(seat__isnull=True).first()
            if unseated_player is None:
                self.stderr.write("All players are seated")
                break
            s = not_full_table.empty_seats().first()
            assert s is not None, "OK I guess I'm too dumb for my own good"
            unseated_player.seat = s
            unseated_player.save()

        self.stdout.write(f"{Player.objects.count()} players at {Table.objects.count()} tables.")
