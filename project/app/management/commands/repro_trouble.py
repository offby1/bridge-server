from app.models import Hand, Player, Table

from django.core.management.base import BaseCommand

"""
We assume you've already loaded the db backup; invoke me like this

$ just restore < 2025-02-01T21:36:20+0000.sql && just manage repro_trouble

"""


def scan_for_bogons():
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
                    bogon_tuples.add((p.name, b.pk, h.pk))
    import pprint

    pprint.pprint(bogon_tuples)


class Command(BaseCommand):
    def handle(self, *args, **options):
        print("Initially:")
        scan_for_bogons()

        Hand.objects.get(pk=318).delete()
        Table.objects.get(pk=21).delete()

        alexis = Player.objects.get_by_name("alexis")
        katie = Player.objects.get_by_name("katie")
        christine = Player.objects.get_by_name("christine")
        craig = Player.objects.get_by_name("craig")

        for p in (alexis, katie, christine, craig):
            p.unseat_me()
            p.save()

        assert alexis.partner == katie
        alexis.break_partnership()
        alexis.partner_with(katie)

        assert christine.partner == craig
        christine.break_partnership()
        christine.partner_with(craig)

        print("After splitsville and re-partering:")
        scan_for_bogons()

        t = Table.objects.create_with_two_partnerships(christine, katie)

        print(f"After creating {t}:")
        scan_for_bogons()
