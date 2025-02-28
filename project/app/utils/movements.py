import collections
import dataclasses
import itertools
from collections.abc import Sequence
from typing import Any

import more_itertools
import tabulate


@dataclasses.dataclass(frozen=True)
class Pair:
    names: str


class PhantomPair(Pair):
    pass


@dataclasses.dataclass(frozen=True)
class Board:
    number: int


def _are_consecutive(numbers: Sequence[int]) -> bool:
    if not numbers:
        return True
    if not numbers[1:]:
        return True
    if numbers[1] != numbers[0] + 1:
        return False
    return _are_consecutive(numbers[1:])


@dataclasses.dataclass(frozen=True)
class BoardGroup:
    letter: str
    boards: tuple[Board, ...]

    def __post_init__(self) -> None:
        assert len(self.letter) == 1
        assert _are_consecutive([b.number for b in self.boards])


@dataclasses.dataclass(frozen=True)
class Quartet:
    ns: Pair
    ew: Pair

    def partition_into_phantoms_and_normals(self) -> tuple[list[Pair], list[Pair]]:
        phantoms: list[Pair] = []
        normals: list[Pair] = []
        for p in (self.ns, self.ew):
            if isinstance(p, PhantomPair):
                phantoms.append(p)
            else:
                normals.append(p)
        return (phantoms, normals)


def _num_tables(*, num_pairs: int) -> tuple[int, bool]:
    rv, overflow = divmod(num_pairs, 2)
    if overflow:
        rv += 1
    return rv, overflow > 0


def make_movement(
    *, boards: Sequence[Board], pairs: Sequence[Pair]
) -> dict[int, list[tuple[Quartet, BoardGroup]]]:
    num_tables, overflow = _num_tables(num_pairs=len(pairs))
    pairs = list(pairs)
    if overflow:
        pairs.append(PhantomPair(names="The Fabulous Phantoms"))

    ns_pairs = pairs[0:num_tables]
    ew_pairs = pairs[num_tables:]

    def ns(table_number: int, round_number: int) -> Pair:
        assert 0 < table_number <= num_tables, f"{table_number=} {num_tables=}"
        assert 0 < round_number <= num_tables, f"{round_number=} {num_tables=}"
        # Standard Mitchell movement: the NS pair at each table stays put
        return ns_pairs[table_number - 1]

    def ew(table_number: int, round_number: int) -> Pair:
        assert 0 < table_number <= num_tables, f"{table_number=} {num_tables=}"
        assert 0 < round_number <= num_tables, f"{round_number=} {num_tables=}"

        # Standard Mitchell movement: the EW pair at each table "rotates" each round
        return ew_pairs[(table_number - round_number) % num_tables]

    num_boards = len(boards)
    boards_per_round = num_boards // num_tables

    board_groups = [
        BoardGroup(letter=letter, boards=tuple(boards))
        for letter, boards in zip(
            "ABCDEFGHIJKLMNOP",
            more_itertools.chunked([Board(n) for n in range(1, num_boards + 1)], boards_per_round),
        )
    ]

    rv: dict[int, list[tuple[Quartet, BoardGroup]]] = collections.defaultdict(list)
    for table_number, round_number in itertools.product(
        range(1, num_tables + 1), range(1, num_tables + 1)
    ):
        q = Quartet(
            ns=ns(table_number=table_number, round_number=round_number),
            ew=ew(table_number=table_number, round_number=round_number),
        )

        rv[table_number - 1].append((q, board_groups[round_number - 1]))
    return rv


# fmt: off

# fmt: on
if __name__ == "__main__":
    pairs = [
        Pair(s)
        for s in (
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
        )
    ]

    for num_pairs in range(3, len(pairs) + 1):
        num_tables, _ = _num_tables(num_pairs=num_pairs)
        for boards_per_round in (2, 3, 4, 5):
            print(f"\n\n{num_pairs=} {boards_per_round=}\n")
            boards = [Board(n) for n in range(1, boards_per_round * num_tables + 1)]

            all_pairs: set[Pair] = set()

            da_movement = make_movement(boards=boards, pairs=pairs[0:num_pairs])

            tabulate_me = []
            for table_number, rounds in da_movement.items():
                this_table: list[Any] = [table_number + 1]
                for quartet, board_group in rounds:
                    phantoms, normals = quartet.partition_into_phantoms_and_normals()
                    if phantoms:
                        assert len(normals) == 1
                        assert len(phantoms) == 1
                        this_table.append(f"{normals[0].names} sits this round out")
                    else:
                        assert len(normals) == 2
                        this_table.append(
                            f"{quartet.ew.names}/{quartet.ns.names} boards {','.join((str(b.number) for b in board_group.boards))}"
                        )
                tabulate_me.append(this_table)
            print(
                tabulate.tabulate(
                    tabulate_me,
                    headers=["Table"] + [f"Round {r}" for r in range(1, len(rounds) + 1)],
                )
            )

            for table_number, rounds in da_movement.items():
                for quartet, board_group in rounds:
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
                for quartet, board_group in rounds:
                    pair_board_combos[(quartet.ns, board_group)] += 1
                    pair_board_combos[(quartet.ew, board_group)] += 1

            [(pair, count)] = pair_board_combos.most_common(1)
            assert count == 1
