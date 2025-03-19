from app.models.player import Player, TooManyBots
from django.core.management.base import BaseCommand

# Creates the necessary directories for daemontools.

# Intended to be run once, just before the web service starts.

# Without this, a fresh web service container will not have any bots.


class Command(BaseCommand):
    def handle(self, *_args, **_options) -> None:
        player_qs = Player.objects.all()
        self.stderr.write(
            f"Bringing up bots: {player_qs.count()} players ... ",
        )

        player_qs = player_qs.filter(currently_seated=True)
        self.stderr.write(f"... of which {player_qs.count()} are currently seated ...")

        player_qs = player_qs.filter(allow_bot_to_play_for_me=True)
        self.stderr.write(
            f"and of *those*, {player_qs.count()} have allowed to bot to play for them."
        )

        for bp in player_qs:
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
