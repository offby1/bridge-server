from __future__ import annotations

import collections
import dataclasses
import itertools
import logging
from collections.abc import Sequence
from typing import Any, TYPE_CHECKING

import more_itertools
import tabulate

from app.models.types import PK

if TYPE_CHECKING:
    from app.models import Board, Player, Tournament


logger = logging.getLogger(__name__)


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


def one_player_from_pair(pair: Pair) -> Player:
    from app.models import Player

    pk = next(iter(pair.id))
    return Player.objects.get(pk=pk)


@dataclasses.dataclass(frozen=True)
class Movement:
    table_settings_by_table_number: dict[int, list[TableSetting]]

    # a "round" is a period where players and boards stay where they are (i.e., at a given table).
    # *within* a round, we play boards_per_round boards.
    def start_round(self, *, tournament: Tournament, round_number: int) -> None:
        from app.models import Player, Table

        assert 0 <= round_number < len(self.table_settings_by_table_number[round_number])
        logger.debug(
            f"Pretend I'm, I dunno, creating tables and seating players and whatnot for {round_number=}"
        )
        tn: int
        table_settings: list[TableSetting]
        for tn, table_settings in sorted(self.table_settings_by_table_number.items()):
            table: Table
            ts = table_settings[round_number]
            phantom_pairs, normal_pairs = ts.quartet.partition_into_phantoms_and_normals()

            if phantom_pairs:
                # Don't create a table; just (TODO) inform the normal pair that they're sitting out this round
                logger.warning(
                    f"Imagine I somehow informed {normal_pairs[0]} that they had to sit out {round_number=}"
                )
                for pk in normal_pairs[0].id:
                    Player.objects.get(pk=pk).unseat_me(
                        reason=f"You're sitting out round {round_number}"
                    )
                continue

            pair1, pair2 = normal_pairs

            pk1 = next(iter(pair1.id))
            player1 = Player.objects.get(pk=pk1)

            pk2 = next(iter(pair2.id))
            player2 = Player.objects.get(pk=pk2)

            table = Table.objects.create_with_two_partnerships(
                player1, player2, tournament=tournament, display_number=tn
            )
            logger.debug(f"{tn=} {table_settings[round_number]=} created {table}")

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

    @classmethod
    def from_pairs(
        cls, *, boards_per_round: int, pairs: Sequence[Pair], tournament: Tournament
    ) -> Movement:
        from app.models import Board

        num_tables, _ = cls.num_tables(num_pairs=len(pairs))
        return cls.from_boards_and_pairs(
            boards=[
                Board.objects.create_from_display_number(display_number=n, tournament=tournament)
                for n in range(1, boards_per_round * num_tables + 1)
            ],
            pairs=pairs,
            tournament=tournament,
        )

    @classmethod
    def from_boards_and_pairs(
        cls, *, boards: Sequence[Board], pairs: Sequence[Pair], tournament: Tournament
    ) -> Movement:
        num_tables, overflow = cls.num_tables(num_pairs=len(pairs))
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
        return cls(table_settings_by_table_number=temp_rv)
