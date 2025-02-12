import app.models
from django.core.management.base import BaseCommand


# The idea: many of our models have methods with names like `_check_this` and `_check_that`.  They take no arguments, and are invoked in the model's overridden "save" method; of course, they check constraints (which cannot be expressed as actual Django model constraints, since they involve more than one instance).

# So: run each of them on each object, and report and problems.

# This is useful for when I've done manual surgery on a database, and have broken something without realizing it.  For
# example: I had a bug whereby we were creating tables with no hands; that triggered assertion failures, so I "fixed" the problem by deleting the bogus tables.  That deleted the seats associated with those tables, leaving some players whose "currently_seated" field was True, but for which no seat existed!


class Command(BaseCommand):
    def handle(self, *_args, **_options) -> None:
        for player in app.models.Player.objects.all():
            for c in ["_check_current_seat", "_check_synthetic"]:
                check = getattr(player, c)
                try:
                    check()
                except AssertionError:
                    self.stderr.write(f"    ****    {player.name=} failed {c=}    ****")
                else:
                    self.stderr.write(f"{player.name} {c} done")

        for seat in app.models.Seat.objects.all():
            for c in ["_check_table_consistency"]:
                check = getattr(seat, c)
                try:
                    check()
                except AssertionError:
                    self.stderr.write(
                        f"    ****    {seat.direction} at {seat.table.pk} failed {c=}    ****"
                    )
                else:
                    self.stderr.write(f"{seat.direction} at {seat.table.pk} {c} done")

        for tournament in app.models.Tournament.objects.all():
            for c in ["_check_no_more_than_one_running_tournament"]:
                check = getattr(tournament, c)
                try:
                    check()
                except AssertionError:
                    self.stderr.write(
                        f"    ****    tournament #{tournament.display_number} failed {c=}    ****"
                    )
                else:
                    self.stderr.write(f"tournament #{tournament.display_number} done")
