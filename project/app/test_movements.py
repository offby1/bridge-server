import collections

import pytest

from app.models import Tournament
import app.models.board
from app.utils.movements import BoardGroup, Movement, Pair


@pytest.mark.django_db
def test_movements_for_realz() -> None:
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
                boards_per_round=boards_per_round, pairs=pairs[0:num_pairs], tournament=t
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
