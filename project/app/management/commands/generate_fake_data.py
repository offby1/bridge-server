import tqdm
from app.models import Player, Table
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db.models import Count
from django.db.utils import IntegrityError
from faker import Faker


class Command(BaseCommand):
    def handle(self, *args, **options):
        fake = Faker()

        with tqdm.tqdm(total=103) as progress_bar:
            while Player.objects.count() < 103:  # deliberately not a multiple of 4
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

        for _ in range(26):
            Table.objects.create(name=f"{Table.objects.count()}")

        while True:
            empty_table = (
                Table.objects.annotate(num_players=Count("player"))
                .filter(num_players__lt=4)
                .first()
            )
            if empty_table is None:
                break
            unseated_player = Player.objects.filter(table__isnull=True).first()
            if unseated_player is None:
                break
            unseated_player.table = empty_table
            unseated_player.save()

        self.stdout.write(f"{Player.objects.count()} players at {Table.objects.count()} tables.")
