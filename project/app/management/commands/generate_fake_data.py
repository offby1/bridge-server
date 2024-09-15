import random

from app.models import HandRecord, Player, Table, logged_queries
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import IntegrityError
from faker import Faker


class Command(BaseCommand):
    def handle(self, *args, **options):
        random.seed(0)  # TODO -- remove me when I'm done debugging

        # Use the same password for everybody, to speed things up :-)
        everybodys_password = make_password(".")

        fake = Faker()
        Faker.seed(0)

        Player.objects.all().delete()
        HandRecord.objects.all().delete()
        Table.objects.all().delete()

        while User.objects.count() < 4:
            existing_bob = User.objects.filter(username="bob")

            username = "bob" if not existing_bob.exists() else fake.unique.first_name().lower()

            User.objects.create(
                username=username,
                password=everybodys_password,
            )

        for u in User.objects.all():
            if Player.objects.count() == 4:
                break

            Player.objects.update_or_create(user=u, is_human=True)

        self.stdout.write(f"Now we have {Player.objects.count()} players.")

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
            with logged_queries():
                not_p1_nor_his_partner = Player.objects.exclude(
                    pk__in={unseated_player_one.pk, unseated_player_one.partner.pk}
                ).all()

                unseated_player_two = not_p1_nor_his_partner.filter(
                    partner__isnull=False, seat__isnull=True
                ).first()

            if not unseated_player_two:
                break

            Table.objects.create_with_two_partnerships(
                unseated_player_one,
                unseated_player_two,
            )

        for p in Player.objects.all():
            self.stdout.write(f"{p.user.username}: {p.partner.user.username}")

        last_table = Table.objects.order_by("-pk").first()
        self.stdout.write(f"{last_table=}")

        self.stdout.write(f"{Player.objects.count()} players at {Table.objects.count()} tables.")
