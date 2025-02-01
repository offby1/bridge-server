from app.models import Hand, Player, Table

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    def handle(self, *args, **options):
        bogon_tuples = set()
        for p in Player.objects.all():
            for b in p.boards_played.all():
                qs = Hand.objects.filter(
                    board=b,
                    table__in=Table.objects.filter(
                        pk__in=p.historical_seat_set.values_list("table_id", flat=True).all()
                    ).all(),
                ).all()

                if qs.count() > 1:
                    for h in qs.order_by("id"):
                        bogon_tuples.add(
                            (p.name, f"Board #{b.display_number} ({b.tournament.pk})", h.pk)
                        )
        import pprint

        pprint.pprint(bogon_tuples)
