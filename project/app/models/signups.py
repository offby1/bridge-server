from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.contrib import admin
from django.db import models


logger = logging.getLogger(__name__)


class TournamentSignupManager(models.Manager):
    if TYPE_CHECKING:
        from app.models import Tournament

    def create_synths_for(self, tour: Tournament):
        from app.models import Player

        for _ in range(2):
            signed_up_pairs = list(tour.signed_up_pairs())

            if len(signed_up_pairs) % 2 == 0:
                break

            p2 = Player.objects.create_synthetic()
            p2.partner = Player.objects.create_synthetic()
            p2.partner.partner = p2
            p2.partner.save()
            p2.save()

            for p in (p2, p2.partner):
                TournamentSignup.objects.create(tournament=tour, player=p)

            logger.debug("Created synths %s and %s for '%s'", p2, p2.partner, tour)

        assert len(signed_up_pairs) % 2 == 0
        logger.debug("%d pairs are waiting", len(signed_up_pairs))


class TournamentSignup(models.Model):
    objects = TournamentSignupManager()

    if TYPE_CHECKING:
        from app.models import Player, Tournament

    tournament = models.ForeignKey["Tournament"]("Tournament", on_delete=models.CASCADE)
    player = models.OneToOneField["Player"]("Player", on_delete=models.CASCADE)

    def __repr__(self) -> str:
        return f"<TournamentSignup pk={self.pk}: {self.player.name} in #{self.tournament.display_number}>"


@admin.register(TournamentSignup)
class TournamentSignupAdmin(admin.ModelAdmin):
    list_display = ["tournament", "player"]
