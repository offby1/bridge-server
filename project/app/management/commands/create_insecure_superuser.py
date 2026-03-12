from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from .utils import is_safe


class Command(BaseCommand):
    def handle(self, *args, **options) -> None:
        if not is_safe(self.stdout):
            msg = "I dunno, creating a superuser with a hard-coded password, in production, seems like a bad idea?"
            raise CommandError(
                msg,
            )

        with transaction.atomic():
            if user := User.objects.filter(is_superuser=True).first():
                self.stdout.write(f"Superuser {user.username!r} already exists.")
                self.stdout.write("`just manage changepassword admin` to change it.")
            else:
                kwargs = {"username": "admin", "password": "admin", "email": "admin@admin.com"}
                User.objects.create_superuser(**kwargs)
                self.stdout.write(f"Created superuser {kwargs!r}.")
