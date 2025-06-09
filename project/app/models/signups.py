from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.contrib import admin
from django.db import models

from app.utils.movements import MAX_ROUNDS

logger = logging.getLogger(__name__)


class TooManySignups(Exception):
    pass


class TournamentSignupManager(models.Manager):
    if TYPE_CHECKING:
        from app.models import Tournament

    def get_or_create(self, defaults=None, **kwargs):
        got = self.filter(**kwargs)
        if got.exists():
            return got.first(), False
        return self.create(**(defaults | kwargs)), True

    def create(self, **kwargs) -> TournamentSignup:
        # TODO -- see if maybe we can have a constraint do this for us, since that sorta sounds like I dunno maybe it'd be more efficient?
        # https://discord.com/channels/856567261900832808/1381640122411515994/1381640122411515994
        if self.count() >= MAX_ROUNDS * 4:
            msg = f"There are already {self.count()} signups, which is the most we can handle"
            raise TooManySignups(msg)
        return super().create(**kwargs)

    def create_synths_for(self, tour: Tournament):
        from app.models import Player

        for _ in range(2):
            signed_up_pairs = list(tour.signed_up_pairs())

            if len(signed_up_pairs) % 2 == 0:
                logger.debug(
                    f"{len(signed_up_pairs)=} is even, so there's no need to create any synthetic players."
                )
                break

            logger.debug(
                f"{len(signed_up_pairs)=} is odd, so we will create one synthetic player partnership (i.e., two players)."
            )
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
