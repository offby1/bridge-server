from app.models.player import Player, TooManyBots
from django.core.management.base import BaseCommand

# Creates the necessary directories for daemontools.

# Intended to be run once, just before the web service starts.

# Without this, a fresh web service container will not have any bots.


class Command(BaseCommand):
    def handle(self, *_args, **_options) -> None:
        self.stderr.write("Synchronizing bot states.")

        for bp in Player.objects.filter(allow_bot_to_play_for_me=True):
            if not bp.currently_seated:
                continue

            self.stderr.write(f"{bp.name} ... ", ending="")

            try:
                bp._control_bot()
            except TooManyBots:
                self.stderr.write("Huh, I guess you *can* have too many bots")
                break
            except OSError as e:
                self.stderr.write(
                    f"{e}; I assume we're not running under docker, so ... outta here",
                )
                break
            self.stderr.write(f"{bp.name} done")
