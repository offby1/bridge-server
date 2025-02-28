import collections
import dataclasses
import itertools
from collections.abc import Sequence
from typing import Any

import more_itertools
import tabulate

from app.models import Board, Tournament
from app.models.types import PK


@dataclasses.dataclass(frozen=True)
class Pair:
    names: str
    id: frozenset[PK]


class PhantomPair(Pair):
    pass


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
        for b in self.boards:
            print(f"{vars(b)=}")
        assert len(self.letter) == 1
        assert _are_consecutive([b.display_number for b in self.boards])


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


@dataclasses.dataclass(frozen=True)
class TableSetting:
    quartet: Quartet
    board_group: BoardGroup


@dataclasses.dataclass(frozen=True)
class Movement:
    table_settings_by_table_number: dict[int, list[TableSetting]]

    def items(self) -> Sequence[tuple[int, list[TableSetting]]]:
        return list(self.table_settings_by_table_number.items())

    @staticmethod
    def num_tables(*, num_pairs: int) -> tuple[int, bool]:
        rv, overflow = divmod(num_pairs, 2)
        if overflow:
            rv += 1
        return rv, overflow > 0

    def display(self) -> None:
        tabulate_me = []
        for table_number, rounds in self.items():
            this_table: list[Any] = [table_number + 1]
            for r in rounds:
                quartet, board_group = r.quartet, r.board_group
                phantoms, normals = quartet.partition_into_phantoms_and_normals()
                if phantoms:
                    this_table.append(f"{normals[0].names} sits this round out")
                else:
                    this_table.append(
                        f"{quartet.ew.names}/{quartet.ns.names} boards {','.join((str(b.display_number) for b in board_group.boards))}"
                    )
            tabulate_me.append(this_table)
        print(tabulate.tabulate(tabulate_me))


def make_movement(
    *, boards: Sequence[Board], pairs: Sequence[Pair], tournament: Tournament
) -> Movement:
    num_tables, overflow = Movement.num_tables(num_pairs=len(pairs))
    pairs = list(pairs)
    if overflow:
        pairs.append(PhantomPair(names="The Fabulous Phantoms", id=frozenset({-1, -2})))

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
            more_itertools.chunked(
                boards,
                boards_per_round,
            ),
        )
    ]

    temp_rv: dict[int, list[TableSetting]] = collections.defaultdict(list)
    for table_number, round_number in itertools.product(range(1, num_tables + 1), repeat=2):
        q = Quartet(
            ns=ns(table_number=table_number, round_number=round_number),
            ew=ew(table_number=table_number, round_number=round_number),
        )

        temp_rv[table_number - 1].append(
            TableSetting(quartet=q, board_group=board_groups[round_number - 1])
        )
    return Movement(table_settings_by_table_number=temp_rv)
