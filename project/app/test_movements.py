import collections
import operator
from typing import TYPE_CHECKING, Any

import more_itertools
import pytest

from django.contrib import auth

from app.models import Player, Tournament
import app.models.board
from app.utils.movements import BoardGroup, Movement, Pair, PhantomPair

from .testutils import play_out_hand


def example_pairs(n: int) -> list[Pair]:
    def ns_first(pair_name: str) -> tuple[bool, int]:
        direction, number = pair_name.split()
        return (bool(direction == "EW"), int(number))

    north_south_names = [
        "NS 1",
        "NS 2",
        "NS 3",
        "NS 4",
        "NS 5",
        "NS 6",
        "NS 7",
    ]
    east_west_names = [
        "EW 1",
        "EW 2",
        "EW 3",
        "EW 4",
        "EW 5",
        "EW 6",
        "EW 7",
    ]
    for index, name in enumerate(
        # Produce a list where all the NS names come first, followed by all the EW names.  That's the order that the movement will put them anyway.
        sorted(
            list(more_itertools.interleave(north_south_names, east_west_names))[0:n], key=ns_first
        )
    ):
        yield Pair(names=name, id=frozenset([2 * index, 2 * index + 1]))


@pytest.mark.django_db
def test_movement_class() -> None:
    for num_pairs in range(3, 13):
        for boards_per_round in (2, 3, 4, 5):
            t = Tournament.objects.create()
            da_movement = Movement.from_pairs(
                boards_per_round_per_table=boards_per_round,
                pairs=list(example_pairs(num_pairs)),
                tournament=t,
            )

            # Ensure there's never more than one phantom
            for table_number, rounds in da_movement.items():
                for r in rounds:
                    quartet, board_group = r.quartet, r.board_group
                    phantoms, normals = quartet.partition_into_phantoms_and_normals()
                    if phantoms:
                        assert len(normals) == 1
                        assert len(phantoms) == 1
                    else:
                        assert len(normals) == 2

            # Ensure every pair plays every board exactly once.
            times_played_by_pair_board_combo = collections.defaultdict(int)
            for table_number, rounds in da_movement.items():
                for r in rounds:
                    quartet, board_group = r.quartet, r.board_group

                    times_played_by_pair_board_combo[(quartet.ns.id, board_group)] += 1
                    times_played_by_pair_board_combo[(quartet.ew.id, board_group)] += 1

            assert set(times_played_by_pair_board_combo.values()) == {1}

            # Ensure every NS pair encounters every EW pair exactly once, and vice-versa.
            matchups = collections.Counter()
            for table_number, rounds in da_movement.items():
                for r in rounds:
                    matchups[r.quartet] += 1

            assert matchups.most_common(1)[0][1] == 1


def test_pairs_and_boards_move(db, everybodys_password) -> None:
    # buid up the simplest possible tournament that has more than one round.
    player_names = ["n1", "e1", "s1", "w1", "n2", "e2", "s2", "w2"]
    for name in player_names:
        Player.objects.create(
            user=auth.models.User.objects.create(username=name, password=everybodys_password),
        )

    open_tournament, _ = Tournament.objects.get_or_create_tournament_open_for_signups(
        boards_per_round_per_table=1
    )

    for p1, p2 in more_itertools.chunked(Player.objects.all(), 2):
        p1.partner_with(p2)
        open_tournament.sign_up(p1)  # p2 gets signed up automatically

    for table in open_tournament.table_set.all():
        play_out_hand(table)

    open_tournament.next_movement_round()

    assert (
        str("ensure we have a new set of boards, n/s have stayed put, but e/w have swapped tables")
        == "cat == dog"
    )
