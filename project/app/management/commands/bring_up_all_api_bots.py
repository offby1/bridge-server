from app.models.player import Player
from django.core.management.base import BaseCommand

# Creates the necessary directories for daemontools.

# Intended to be run once, just before the web service starts.

# Without this, a fresh web service container will not have any bots.


class Command(BaseCommand):
    def handle(self, *_args, **_options) -> None:
        for bp in Player.objects.filter(
            player__currently_seated=True,
        ).filter(allow_bot_to_play_for_me=True):
            self.stderr.write(f"{bp.name} ... ", ending="")

            try:
                bp.toggle_bot(True)
            except OSError as e:
                self.stderr.write(
                    f"{e}; I assume we're not running under docker, so ... outta here",
                )
                break
            self.stderr.write(f"{bp.name} done")
