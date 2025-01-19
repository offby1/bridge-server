from app.models.player import Player
from app.models.table import Table
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    def handle(self, *_args, **_options) -> None:
        Table.objects.all().update(tempo_seconds=0)

        for player in Player.objects.filter(currently_seated=True):
            try:
                player.toggle_bot(True)
            except OSError as e:
                self.stderr.write(
                    f"{e}; I assume we're not running under docker, so ... outta here",
                )
                break

            self.stderr.write(f"{player.name} done")
