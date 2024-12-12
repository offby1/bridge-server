import app.models
import app.views
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    def handle(self, *_args, **_options):
        self.stderr.write("About to bring up all the API bots.")

        for player in app.models.Player.objects.filter(allow_bot_to_play_for_me=True).filter(
            currently_seated=True
        ):
            self.stderr.write(f"{player.name} ... ", ending="")
            try:
                app.views.player.control_bot_for_player(player)
            except OSError as e:
                self.stderr.write(
                    f"{e}; I assume we're not running under docker, so ... outta here"
                )
                break
            self.stderr.write(f"{player.name} done")
