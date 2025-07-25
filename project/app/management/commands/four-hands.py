from __future__ import annotations
import subprocess

from django.core.management.base import BaseCommand
from django.urls import reverse


import app.models
import app.testutils


class Command(BaseCommand):
    def handle(self, *args, **options) -> None:
        # make one user human
        p1 = app.models.Player.objects.first()

        assert p1 is not None

        # This skirts a safeguard in Player.save()
        app.models.Player.objects.filter(pk=p1.pk).update(
            synthetic=False, allow_bot_to_play_for_me=False
        )

        p1.user.username = "bob"
        p1.user.save()

        h: app.models.Hand = p1.current_hand

        app.testutils.play_out_hand(h)

        # Find a board that bob has completed, and look at some incomplete hand that uses it.

        viewable_hand = (
            app.models.Hand.objects.filter(board=h.board)
            .exclude(id=h.id)
            .filter(is_complete=False)
            .first()
        )
        assert viewable_hand is not None
        subprocess.run(
            [
                "open",
                "http://localhost:9000"
                + reverse("app:hand-dispatch", kwargs=dict(pk=viewable_hand.pk)),
            ]
        )
