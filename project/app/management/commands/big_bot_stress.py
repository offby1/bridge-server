import datetime
import os

from app.models.player import Player, TooManyBots
from app.models.table import Table
from app.models.signups import TournamentSignup
from app.models.tournament import Tournament
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


class Command(BaseCommand):
    def handle(self, *_args, **_options) -> None:
        is_safe = False

        if settings.DEBUG:
            is_safe = True

        if os.environ.get("DOCKER_CONTEXT") == "hetz":
            is_safe = True

        self.stderr.write(f"{settings.DEBUG=} {os.environ.get('DOCKER_CONTEXT')}")

        if not is_safe:
            raise CommandError(
                "I dunno, creating a fleet of killer bots, in production, seems like a bad idea?"
            )

        t: Tournament
        t, _ = Tournament.objects.get_or_create_tournament_open_for_signups()

        with transaction.atomic():
            for p in (
                Player.objects.filter(currently_seated=False)
                .filter(partner__currently_seated=False)
                .all()
            ):
                if TournamentSignup.objects.filter(player__in={p, p.partner}).exists():
                    self.stderr.write(f"{p.name} is already signed up for some tournament")
                else:
                    t.sign_up(p)

            t.signup_deadline = datetime.datetime.now(tz=datetime.UTC)
            t.save()

        num_tables_updated: int = Table.objects.all().update(tempo_seconds=0)
        self.stderr.write(f"Sped up {num_tables_updated} tables")

        num_bots_enabled = 0
        player: Player
        for player in Player.objects.filter(currently_seated=True):
            try:
                player.toggle_bot(True)
            except TooManyBots:
                self.stderr.write("Huh, I guess you *can* have too many bots")
                break
            except OSError as e:
                self.stderr.write(
                    f"{e}; I assume we're not running under docker, so ... outta here",
                )
                break
            else:
                num_bots_enabled += 1
                self.stderr.write(f"{player.name} done")

        self.stderr.write(f"Enabled {num_bots_enabled} bots")
