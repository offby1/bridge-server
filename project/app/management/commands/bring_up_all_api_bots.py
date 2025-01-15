from app.models.player import BotPlayer
from django.core.management.base import BaseCommand

# Creates the necessary directories for daemontools.

# Intended to be run once, just before the web service starts.

# Without this, a fresh web service container will not have any bots.


class Command(BaseCommand):
    def handle(self, *_args, **_options) -> None:
        for bp in BotPlayer.objects.filter(
            player__currently_seated=True,
        ):
            self.stderr.write(f"{bp.player.name} ... ", ending="")

            try:
                bp.player.control_bot()
            except OSError as e:
                self.stderr.write(
                    f"{e}; I assume we're not running under docker, so ... outta here",
                )
                break
            self.stderr.write(f"{bp.player.name} done")
