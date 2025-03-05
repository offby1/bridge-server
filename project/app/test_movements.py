import collections

import more_itertools
import pytest

from django.contrib import auth

from app.models import Player, Tournament
import app.models.board
from app.utils.movements import BoardGroup, Movement, Pair

from .testutils import play_out_hand


@pytest.mark.django_db
def test_movement_class() -> None:
    pairs = [
        Pair(names=s, id=frozenset([2 * index, 2 * index + 1]))
        for index, s in enumerate(
            [
                "NS 1",
                "NS 2",
                "NS 3",
                "NS 4",
                "NS 5",
                "NS 6",
                "NS 7",
                "EW 1",
                "EW 2",
                "EW 3",
                "EW 4",
                "EW 5",
                "EW 6",
            ]
        )
    ]

    for num_pairs in range(3, len(pairs) + 1):
        num_tables, _ = Movement.num_tables(num_pairs=num_pairs)
        for boards_per_round in (2, 3, 4, 5):
            t = Tournament.objects.create()
            print(f"\n\n{num_pairs=} {boards_per_round=}\n")

            all_pairs: set[Pair] = set()

            da_movement = Movement.from_pairs(
                boards_per_round_per_table=boards_per_round, pairs=pairs[0:num_pairs], tournament=t
            )

            for table_number, rounds in da_movement.items():
                for r in rounds:
                    quartet, board_group = r.quartet, r.board_group
                    phantoms, normals = quartet.partition_into_phantoms_and_normals()
                    if phantoms:
                        assert len(normals) == 1
                        assert len(phantoms) == 1
                    else:
                        assert len(normals) == 2

            for table_number, rounds in da_movement.items():
                for r in rounds:
                    quartet, board_group = r.quartet, r.board_group
                    pairs_in_this_round = set()
                    pairs_in_this_round.add(quartet.ns)
                    pairs_in_this_round.add(quartet.ew)

            if all_pairs:
                import pprint

                # Ensure every pair plays in every round
                assert (
                    all_pairs == pairs_in_this_round
                ), f"{pprint.pformat(all_pairs)} but {pprint.pformat(pairs_in_this_round)}"
            else:
                all_pairs = pairs_in_this_round

            pair_board_combos: collections.Counter[tuple[Pair, BoardGroup]] = collections.Counter()
            for table_number, rounds in da_movement.items():
                for r in rounds:
                    quartet, board_group = r.quartet, r.board_group
                    pair_board_combos[(quartet.ns, board_group)] += 1
                    pair_board_combos[(quartet.ew, board_group)] += 1

            [(pair, count)] = pair_board_combos.most_common(1)
            assert count == 1


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
