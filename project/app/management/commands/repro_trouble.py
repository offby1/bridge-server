from app.models import Hand, Player, Table

from django.core.management.base import BaseCommand

"""
We assume you've already loaded the db backup
"""


class Command(BaseCommand):
    def handle(self, *args, **options):
        Hand.objects.get(pk=318).delete()
        Table.objects.get(pk=21).delete()
