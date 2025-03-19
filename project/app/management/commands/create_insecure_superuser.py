from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db.utils import IntegrityError

from .utils import is_safe


class Command(BaseCommand):
    def handle(self, *args, **options) -> None:
        if not is_safe(self.stderr):
            msg = "I dunno, creating a superuser with a hard-coded password, in production, seems like a bad idea?"
            raise CommandError(
                msg,
            )

        username = "admin"
        try:
            User.objects.create_superuser(username=username, password="admin")
        except IntegrityError as e:
            self.stderr.write(f"Superuser {username!r} probably already exists -- {e}")
