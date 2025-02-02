from app.models import Hand, Player, Table

from django.core.management.base import BaseCommand

"""
We assume you've already loaded the db backup; invoke me like this

$ just restore < 2025-02-01T21:36:20+0000.sql && just manage repro_trouble

"""


class Command(BaseCommand):
    def handle(self, *args, **options):
        Hand.objects.get(pk=318).delete()
        Table.objects.get(pk=21).delete()

        alexis = Player.objects.get_by_name("alexis")
        katie = Player.objects.get_by_name("katie")

        assert alexis.partner == katie
        alexis.break_partnership()
        alexis.partner_with(katie)

        christine = Player.objects.get_by_name("christine")
        craig = Player.objects.get_by_name("craig")

        assert christine.partner == craig
        christine.break_partnership()
        christine.partner_with(craig)

        t = Table.objects.create_with_two_partnerships(christine, katie)

        print(t)
