import json

from app.models import Table
from app.views.table import details
from django.core.management.base import BaseCommand
from django.test.client import RequestFactory


class Command(BaseCommand):
    def handle(self, *args, **options):
        rf = RequestFactory()
        for table_id in Table.objects.values_list(flat=True).all():
            request = rf.post(
                "/woteva/",
                data={"who pokes me": json.dumps({"table_id": table_id, "direction": 12345})},
            )
            details.poke_de_bot(request)
            self.stdout.write(f"Poked {table_id=}")
