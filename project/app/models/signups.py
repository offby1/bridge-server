from typing import TYPE_CHECKING

from django.contrib import admin
from django.db import models


class TournamentSignup(models.Model):
    if TYPE_CHECKING:
        from app.models import Player, Tournament

    tournament = models.ForeignKey["Tournament"]("Tournament", on_delete=models.CASCADE)
    player = models.OneToOneField["Player"]("Player", on_delete=models.CASCADE)

    def __repr__(self) -> str:
        return f"<TournamentSignup pk={self.pk}: {self.player.name} in #{self.tournament.display_number}>"


@admin.register(TournamentSignup)
class TournamentSignupAdmin(admin.ModelAdmin):
    list_display = ["tournament", "player"]
