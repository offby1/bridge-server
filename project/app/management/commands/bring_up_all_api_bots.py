import app.models
import app.views
from django.core.management.base import BaseCommand

# Creates the necessary directories for daemontools.

# Intended to be run once, just before the web service starts.

# Without this, a fresh web service container will not have any bots.


class Command(BaseCommand):
    def handle(self, *_args, **_options) -> None:
        # Don't start a bot for every player, if there are "a lot" of players.  And why?  Because we will exhaust the number of postgres connections :-|
        # Yeah, I could increase it, but first I'd like to know why we use 'em all up so quickly.
        # https://www.postgresql.org/docs/current/runtime-config-connection.html#GUC-MAX-CONNECTIONS
        max_number = 40

        self.stderr.write(f"About to bring up (no more than {max_number}) the API bots.")

        for player in app.models.Player.objects.filter(allow_bot_to_play_for_me=True).filter(
            currently_seated=True,
        )[0:max_number]:
            self.stderr.write(f"{player.name} ... ", ending="")

            try:
                app.views.player.control_bot_for_player(player)
            except OSError as e:
                self.stderr.write(
                    f"{e}; I assume we're not running under docker, so ... outta here",
                )
                break
            self.stderr.write(f"{player.name} done")
