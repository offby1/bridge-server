import tqdm
from app.models import Hand, Player, Seat, Table
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db.models import Count
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

        with tqdm.tqdm(total=options["tables"]) as progress_bar:
            while Table.objects.count() < options["tables"]:
                t = Table.objects.create(name=f"{Table.objects.count()}")
                Seat.create_for_table(t)
                progress_bar.update()

        while True:
            not_full_table = Table.non_full_table()
            if not_full_table is None:
                self.stderr.write("All tables are full.")
                break

            unseated_player = Player.objects.filter(seat__isnull=True).first()

            if unseated_player is None:
                self.stderr.write("All players are seated.")
                break

            unseated_player.seat = not_full_table.empty_seats().first()
            unseated_player.save()

        for t in tqdm.tqdm(
            Table.objects.annotate(num_players=Count("seat__player")).filter(num_players=4),
        ):
            h = Hand.objects.create(table_played_at=t)
            h.deal()

        self.stdout.write(f"{Player.objects.count()} players at {Table.objects.count()} tables.")
