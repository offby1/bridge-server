import app.models
from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    def handle(self, *_args, **_options) -> None:
        now = timezone.now()
        app.models.Tournament.objects.filter(
            is_complete=False, signup_deadline__isnull=False
        ).update(signup_deadline=now)
