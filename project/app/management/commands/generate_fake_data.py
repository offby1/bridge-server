from __future__ import annotations

import tqdm
from app.models import Player, Table, Tournament
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from faker import Faker


class Command(BaseCommand):
    def __init__(self) -> None:
        # Use the same password for everybody, to speed things up :-)
        self.everybodys_password = make_password(".")
        super().__init__()

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--players",
            default=40,
            type=int,
        )

    def maybe_create_player(self, username: str) -> tuple[Player, bool]:
        user, _ = User.objects.get_or_create(
            username=username,
            defaults={"password": self.everybodys_password},
        )
        return Player.objects.get_or_create(
            user=user,
        )

    def handle(self, *args, **options) -> None:
        fake = Faker()
        Faker.seed(0)

        new_players = []

        with tqdm.tqdm(desc="players", total=options["players"], unit="p") as progress_bar:
            while Player.objects.count() < options["players"]:
                # Make sure we always have "bob", because his name is easy to type, and to remember :-)
                if not Player.objects.exists():
                    username = "bob"
                else:
                    username = fake.unique.first_name().lower()

                player, created = self.maybe_create_player(username)
                if created:
                    new_players.append(player)

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
                partner__isnull=False,
                seat__isnull=True,
            ).first()

            if not unseated_player_one:
                break

            # find another unseated partnership

            unseated_player_two = (
                Player.objects.exclude(
                    pk__in={unseated_player_one.pk, unseated_player_one.partner.pk},
                )
                .filter(partner__isnull=False, seat__isnull=True)
                .first()
            )

            if not unseated_player_two:
                break

            # Ensure we have at least one tournament.
            if not Tournament.objects.exists():
                t = Tournament.objects.create()
                self.stdout.write(f"Created {t}")

            Table.objects.create_with_two_partnerships(
                unseated_player_one,
                unseated_player_two,
            )

        # Don't ask me how but I've seen tables without hands
        last_table: Table | None = Table.objects.exclude(hand__isnull=True).order_by("-pk").first()
        assert last_table is not None

        # Now create a couple of unseated players.
        while True:
            count = Player.objects.filter(seat__isnull=True).count()
            if count >= 3:
                break
            player, created = self.maybe_create_player(fake.unique.first_name().lower())
            self.stdout.write(f"{player} {created=}")

        self.stdout.write(f"{Player.objects.count()} players at {Table.objects.count()} tables.")
