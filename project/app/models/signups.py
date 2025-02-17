from typing import TYPE_CHECKING

from django.db import models

if TYPE_CHECKING:
    from app.models import Player, Tournament


class TournamentSignups(models.Model):
    tournament = models.ForeignKey["Tournament"]("Tournament", on_delete=models.CASCADE)
    player = models.OneToOneField["Player"]("Player", on_delete=models.CASCADE)
