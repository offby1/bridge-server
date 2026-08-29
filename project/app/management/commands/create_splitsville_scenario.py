"""Build the tournament that the `three_tables_one_pair_split_mid_round` fixture holds.

Three tables, two boards a round.  Every table finishes its first board; then, while all
three are partway through their second, one pair goes Splitsville.  That leaves the
tournament in the state worth looking at: one table dead mid-round with a board it will
never play, two tables still going, and nothing yet scored.

Run this against an empty database and dump the result:

    just drop && just migrate
    just manage create_splitsville_scenario
    just dumpdata

Everybody is a human with password ".", and nobody has the bot flag set, so the scenario
stays put until you act on it yourself.
"""

from __future__ import annotations

import datetime

from app.models import Hand, Player, Tournament
from app.models.tournament import _do_signup_expired_stuff
from django.contrib import auth
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from bridge.contract import Bid, Pass

PAIRS = [
    ("Ella Fitzgerald", "Louis Armstrong"),
    ("Bessie Smith", "Ma Rainey"),
    ("Duke Ellington", "Billy Strayhorn"),
    ("Charlie Parker", "Dizzy Gillespie"),
    ("Thelonious Monk", "Bud Powell"),
    ("Sarah Vaughan", "Carmen McRae"),
]

BOARDS_PER_ROUND_PER_TABLE = 2


def _make_player(name: str) -> Player:
    user = auth.models.User.objects.create(username=name)
    user.set_password(".")
    user.save()
    return Player.objects.create(user=user)


def _play_out(hand: Hand) -> None:
    """Open with the cheapest bid, pass it out, then play all thirteen tricks."""
    while hand.player_who_may_call is not None:
        legal = hand.get_xscript().auction.legal_calls()
        if hand.call_set.exists():
            call = Pass
        else:
            call = next(c for c in legal if isinstance(c, Bid))
        hand.add_call(call=call)

    while (seat := hand.next_seat_to_play) is not None:
        hand.add_play_from_model_player(
            player=hand.player_who_controls_seat(seat, right_this_second=True),
            card=hand.get_xscript().slightly_less_dumb_play().card,
        )

    if not hand.is_complete:
        msg = f"{hand} should be complete by now"
        raise CommandError(msg)


class Command(BaseCommand):
    help = "Three tables, two boards a round, one pair walking out partway through round one"

    def handle(self, *args, **options) -> None:
        if Tournament.objects.exists():
            msg = (
                "This wants an empty database, so that the fixture it produces holds"
                " nothing but the scenario.  Try `just drop && just migrate` first."
            )
            raise CommandError(msg)

        with transaction.atomic():
            tour = Tournament.objects.create(boards_per_round_per_table=BOARDS_PER_ROUND_PER_TABLE)

            for first, second in PAIRS:
                p1 = _make_player(first)
                p2 = _make_player(second)
                p1.partner_with(p2)
                tour.sign_up_player_and_partner(p1)

            # Signups have to be open to accept anybody and closed to deal any boards.
            tour.signup_deadline = timezone.now() - datetime.timedelta(seconds=10)
            tour.save()
            _do_signup_expired_stuff(tour)

        movement = tour.get_movement()
        num_tables = len(movement.table_settings_by_zb_table_number)
        if num_tables != 3:
            msg = f"Expected three tables, got {num_tables}"
            raise CommandError(msg)

        # Round one, first board, at all three tables.  Finishing one deals that table
        # its second board, which is the board somebody is about to walk out of.
        for table in range(1, num_tables + 1):
            hand = tour.hands().get(table_display_number=table)
            _play_out(hand)
            self.stdout.write(f"Table {table} played {hand.board}")

        in_progress = tour.hands().filter(is_complete=False, abandoned_because__isnull=True)
        if in_progress.count() != num_tables:
            msg = f"Expected {num_tables} boards under way, found {in_progress.count()}"
            raise CommandError(msg)

        quitter = tour.hands().get(table_display_number=1, is_complete=False).North
        partner = quitter.partner
        quitter.break_partnership()

        self.stdout.write(
            self.style.SUCCESS(
                f"{quitter.name} and {partner.name} have left tournament"
                f" #{tour.display_number}, from table 1"
            )
        )

        tour.refresh_from_db()
        for h in tour.hands().order_by("table_display_number", "board__display_number"):
            state = "abandoned" if h.is_abandoned else "complete" if h.is_complete else "underway"
            self.stdout.write(f"  table {h.table_display_number} {h.board} -- {state}")
