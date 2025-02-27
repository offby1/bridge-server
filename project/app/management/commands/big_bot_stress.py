import datetime
import os

from app.models.player import Player, TooManyBots
from app.models.table import Table
from app.models.signups import TournamentSignup
from app.models.tournament import Tournament, check_for_expirations
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


class Command(BaseCommand):
    def handle(self, *_args, **_options) -> None:
        is_safe = False

        if settings.DEBUG:
            is_safe = True

        if os.environ.get("DOCKER_CONTEXT") in {"hetz", "orbstack"}:
            is_safe = True

        self.stderr.write(f"{settings.DEBUG=} {os.environ.get('DOCKER_CONTEXT')}")

        if not is_safe:
            raise CommandError(
                "I dunno, creating a fleet of killer bots, in production, seems like a bad idea?"
            )

        t: Tournament
        with transaction.atomic():
            t, _ = Tournament.objects.get_or_create_tournament_open_for_signups()

            p: Player
            for p in Player.objects.order_by("user__username").all():
                if p.currently_seated:
                    p.unseat_me()
                    self.stderr.write(f"Unseated {p.name}")

                if p.partner is not None and p.partner.currently_seated:
                    p.partner.unseat_me()
                    self.stderr.write(f"Unseated {p.partner.name}")

                if TournamentSignup.objects.filter(player__in={p, p.partner}).exists():
                    TournamentSignup.objects.filter(player__in={p, p.partner}).delete()
                    self.stderr.write(
                        f"{p.name} was already signed up for some tournament, but ain't no' mo'"
                    )

                t.sign_up(p)
                self.stderr.write(f"Signed {p.name} up for t#{t.display_number}")

            t.signup_deadline = datetime.datetime.now(tz=datetime.UTC)

            # saving, and checking for expirations, has all kindsa side effects.

            # if the tournament is complete (it shouldn't be, but ...) then saving will delete all the signups, and put
            # all the players into the lobby.

            t.save()

            # - complete the tournament if all the hands have been played
            # - add some boards to the tournament
            # - seat everyone at newly-created tables, creating (and signing up) some synths if necessary
            check_for_expirations(sender="big_bot_stress")

            call_command("bring_up_all_api_bots")

            tables_updated: list[str] = []
            for table in Table.objects.all():
                table.tempo_seconds = 0
                table.save()
                tables_updated.append(str(table.pk))

            self.stderr.write(f"Sped up tables {', '.join(tables_updated)}")
