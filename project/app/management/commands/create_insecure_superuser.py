from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db.utils import IntegrityError


class Command(BaseCommand):
    def handle(self, *args, **options):
        if settings.DEBUG:
            username = "admin"
            try:
                User.objects.create_superuser(username=username, password="admin")
            except IntegrityError as e:
                self.stderr.write(f"Superuser {username!r} probably already exists -- {e}")
        else:
            self.stderr.write(
                "I dunno, creating a superuser with a hard-coded password, in production, seems like a bad idea?",
            )
