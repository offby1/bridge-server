from app.models import Player, Table
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db.utils import IntegrityError
from faker import Faker


class Command(BaseCommand):
    def handle(self, *args, **options):
        fake = Faker()

        for index in range(100):
            try:
                django_user = User.objects.create(username=fake.first_name())
            except IntegrityError:
                continue
            Player.objects.create(user=django_user)

        for index in range(10):
            Table.objects.create(name=f"Table {index}")
