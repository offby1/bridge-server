from __future__ import annotations

import sys
import timeit

from app.models import Player
from app.views import player
from django.core.management.base import BaseCommand
from django.test.client import RequestFactory


class Command(BaseCommand):
    def handle(self, *args, **options):
        rf = RequestFactory()
        request = rf.get("/woteva/")
        request.user = Player.objects.get_by_name("bob").user

        number = 5
        total_seconds = timeit.timeit(lambda: player.player_list_view(request), number=number)
        sys.stderr.write(
            f"{total_seconds=} for {number=} calls, mean {total_seconds / number} seconds\n",
        )
