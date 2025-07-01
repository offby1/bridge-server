import datetime

from app.models.player import Player
from app.models.signups import TooManySignups, TournamentSignup
from app.models.tournament import Tournament, check_for_expirations
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models.query import QuerySet

from .utils import is_safe


# In [1]: from django.contrib.auth.hashers import make_password
# In [2]: make_password(".")
# Out[2]: 'pbkdf2_sha256$870000$2hIscex1sYiQd86rzIuNEb$C1t3fgjQJ00VLQA6H7Hg25GGjkyLc9CBfkzNTSbqYTU='
everybodys_password = (
    "pbkdf2_sha256$870000$2hIscex1sYiQd86rzIuNEb$C1t3fgjQJ00VLQA6H7Hg25GGjkyLc9CBfkzNTSbqYTU="
)


class Command(BaseCommand):
    def add_arguments(self, parser) -> None:
        parser.add_argument("--tempo-seconds", type=int, default=5)

        group = parser.add_mutually_exclusive_group()
        group.add_argument("--min-players", type=int, default=0)
        group.add_argument("--tiny", default=False, action="store_true")

    def handle(self, *_args, **options) -> None:
        if not is_safe(self.stderr):
            msg = "I dunno, creating a fleet of killer bots, in production, seems like a bad idea?"
            raise CommandError(
                msg,
            )

        call_command("create_insecure_superuser")

        t: Tournament
        with transaction.atomic():
            boards_per_round_per_table = 3
            if options.get("tiny", False):
                boards_per_round_per_table = 1
            self.stderr.write(f"{options=}; {boards_per_round_per_table=}")

            t, _ = Tournament.objects.get_or_create_tournament_open_for_signups(
                boards_per_round_per_table=boards_per_round_per_table,
                tempo_seconds=options["tempo_seconds"],
            )

            if (num_players := options.get("min_players", 0)) == 0:
                if options.get("tiny", False):
                    num_players = 8

            def synths() -> QuerySet:
                return Player.objects.order_by("user__username").filter(synthetic=True)

            while synths().count() < num_players:
                p1 = Player.objects.create_synthetic()
                p2 = Player.objects.create_synthetic()
                p1.partner = p2
                p2.partner = p1
                p1.save()
                p2.save()
                self.stderr.write(f"Created partners {p1.name} and {p2.name}")

            for p in synths().filter(partner__isnull=True):
                self.stderr.write(f"{p.name} has no partner; making another synth")
                p.partner = Player.objects.create_synthetic()
                p.partner.partner = p
                p.save()
                p.partner.save()

            for p in synths():
                if p.currently_seated:
                    p.unseat_partnership()

                if TournamentSignup.objects.filter(player__in={p, p.partner}).exists():
                    TournamentSignup.objects.filter(player__in={p, p.partner}).delete()
                    self.stderr.write(
                        f"{p.name} was already signed up for some tournament, but ain't no' mo'",
                    )

                try:
                    t.sign_up_player_and_partner(p)
                except TooManySignups as e:
                    self.stderr.write(f"{e}; will stop signing up players")
                    break
                self.stderr.write(f"Signed {p.name} up for t#{t.display_number}")
                p.user.password = everybodys_password
                p.user.save()
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

            call_command("synchronize_bot_states")
