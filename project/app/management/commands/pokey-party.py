import json
from argparse import ArgumentParser

from app.models import Table
from app.views.table import details
from django.core.management.base import BaseCommand
from django.test.client import RequestFactory


class Command(BaseCommand):
    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            "--tempo",
            type=float,
        )

    def handle(self, *args, **options) -> None:
        if options["tempo"] is not None:
            Table.objects.all().update(tempo_seconds=options["tempo"])

        rf = RequestFactory()
        for table_id in Table.objects.values_list(flat=True).all():
            request = rf.post(
                "/woteva/",
                data={"who pokes me": json.dumps({"table_id": table_id, "direction": 12345})},
            )
            details.poke_de_bot(request)
            self.stdout.write(f"Poked {table_id=}")
