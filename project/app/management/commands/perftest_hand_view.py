from __future__ import annotations

import sys
import timeit

from app.models import Hand, Player
from app.views import hand
from django.core.management.base import BaseCommand
from django.test.client import RequestFactory


class Command(BaseCommand):
    def handle(self, *args, **options):
        rf = RequestFactory()
        request = rf.get("/woteva/")
        request.user = Player.objects.get_by_name("bob").user

        h = Hand.objects.first()
        assert h is not None

        number = 5
        total_seconds = timeit.timeit(lambda: hand.hand_detail_view(request, h.pk), number=number)
        sys.stderr.write(
            f"{total_seconds=} for {number=} calls, mean {total_seconds / number} seconds\n",
        )
