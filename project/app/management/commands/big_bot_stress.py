import datetime
import os

from app.models.player import Player
from app.models.table import Table
from app.models.signups import TournamentSignup
from app.models.tournament import Tournament, check_for_expirations
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


class Command(BaseCommand):
    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group()
        group.add_argument("--min-players", type=int, default=0)
        group.add_argument("--tiny", default=False, action="store_true")

    def handle(self, *_args, **options) -> None:
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

        call_command("create_insecure_superuser")

        t: Tournament
        with transaction.atomic():
            boards_per_round_per_table = 3
            if options.get("tiny", False):
                boards_per_round_per_table = 1
            self.stderr.write(f"{options=}; {boards_per_round_per_table=}")

            t, _ = Tournament.objects.get_or_create_tournament_open_for_signups(
                boards_per_round_per_table=boards_per_round_per_table
            )

            p: Player

            if (num_players := options.get("min_players", 0)) == 0:
                if options.get("tiny", False):
                    num_players = 8

            while Player.objects.order_by("user__username").count() < num_players:
                p1 = Player.objects.create_synthetic()
                p2 = Player.objects.create_synthetic()
                p1.partner = p2
                p2.partner = p1
                p1.save()
                p2.save()
                self.stderr.write(f"Created partners {p1.name} and {p2.name}")

            for p in Player.objects.filter(partner__isnull=True):
                self.stderr.write(f"{p.name} has no partner; making another synth")
                p.partner = Player.objects.create_synthetic()
                p.partner.partner = p
                p.save()
                p.partner.save()

            for p in Player.objects.order_by("user__username").all():
                if p.currently_seated:
                    p.unseat_partnership()

                if TournamentSignup.objects.filter(player__in={p, p.partner}).exists():
                    TournamentSignup.objects.filter(player__in={p, p.partner}).delete()
                    self.stderr.write(
                        f"{p.name} was already signed up for some tournament, but ain't no' mo'"
                    )

                t.sign_up(p)
                self.stderr.write(f"Signed {p.name} up for t#{t.display_number}")
                p.toggle_bot(True)

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
