from __future__ import annotations

import collections
from collections.abc import Generator
import dataclasses
import itertools
import logging
from collections.abc import Sequence
from typing import TYPE_CHECKING

import more_itertools
import tabulate

from app.models.types import PK

if TYPE_CHECKING:
    from app.models import Board, Tournament


logger = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True, order=True)
class Pair:
    # Keep id first so that "names" has no effect on the ordering.
    id: frozenset[PK]
    names: str


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

    def names(self) -> str:
        return f"{self.ns.names}/{self.ew.names}"


@dataclasses.dataclass(frozen=True)
class PlayersAndBoardsForOneRound:
    quartet: Quartet
    board_group: BoardGroup


def _group_letter(round_number: int) -> str:
    return "ABCDEFGHIJKLMNOP"[round_number]


@dataclasses.dataclass(frozen=True)
class Movement:
    boards_per_round_per_table: int  # redundant, but handy
    # The number of tables always equals the number of rounds.
    table_settings_by_table_number: dict[int, list[PlayersAndBoardsForOneRound]]

    def __post_init__(self):
        tabulate_me = []
        for tn, rounds in self.table_settings_by_table_number.items():
            row = [tn]

            for r in rounds:
                quartet, board_group = r.quartet, r.board_group
                row.append(f"{quartet.names()} plays {board_group}")
            tabulate_me.append(row)
        print(
            tabulate.tabulate(
                tabulate_me, headers=["table"] + [f"Round {n + 1}" for n in range(len(rounds))]
            )
        )

    # a "round" is a period where players and boards stay where they are (i.e., at a given table).
    # *within* a round, we play boards_per_round_per_table boards (per table!).
    def start_round(self, *, tournament: Tournament, round_number: int) -> None:
        from app.models import Player, Table

        assert 0 <= round_number
        if round_number >= len(self.table_settings_by_table_number[0]):
            from app.models import NoMoreBoards

            msg = f"Tournament #{tournament.display_number} only has {len(self.table_settings_by_table_number[0])} rounds, but you asked for {round_number=}"
            raise NoMoreBoards(msg)
        logger.debug(f"Creating tables and seating players and whatnot for {round_number=}")
        tn: int
        table_settings: list[PlayersAndBoardsForOneRound]
        for tn, table_settings in sorted(self.table_settings_by_table_number.items()):
            table: Table
            ts = table_settings[round_number]
            phantom_pairs, normal_pairs = ts.quartet.partition_into_phantoms_and_normals()

            if phantom_pairs:
                assert len(normal_pairs) == 1
                assert len(phantom_pairs) == 1

                # Don't create a table; just inform the normal pair that they're sitting out this round
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
                player1, player2, tournament=tournament, display_number=tn + 1
            )
            logger.debug(f"{tn=} {table_settings[round_number]=} created {table}")
            table.next_board()

    def items(self) -> Sequence[tuple[int, list[PlayersAndBoardsForOneRound]]]:
        return list(self.table_settings_by_table_number.items())

    @staticmethod
    def num_tables(*, num_pairs: int) -> tuple[int, bool]:
        rv, overflow = divmod(num_pairs, 2)
        if rv == 0:
            logger.warning(f"Hmm, {num_pairs=} so of course {rv=}")
        if overflow:
            rv += 1
        return rv, overflow > 0

    @staticmethod
    def make_boards(
        *, boards_per_round_per_table: int, num_tables: int, tournament: Tournament
    ) -> Generator[Board]:
        from app.models import Board

        for group_index, display_numbers in enumerate(
            more_itertools.chunked(
                range(1, boards_per_round_per_table * num_tables + 1),
                boards_per_round_per_table,
            )
        ):
            for n in display_numbers:
                a_board, _ = Board.objects.get_or_create_from_display_number(
                    group=_group_letter(group_index), display_number=n, tournament=tournament
                )
                yield a_board

    @classmethod
    def from_pairs(
        cls,
        *,
        boards_per_round_per_table: int,
        pairs: Sequence[Pair],
        tournament: Tournament,
    ) -> Movement:
        num_tables, overflow = cls.num_tables(num_pairs=len(pairs))

        # Sort so that if we later construct movement with the same pairs, albeit perhaps a different order, we get
        # *exactly* the same movement back.
        # In practice our callers already sort, but ... it probably can't hurt to be sure.
        pairs = sorted(pairs)

        if overflow:
            logger.debug(f"{pairs=}; {num_tables=} but {overflow=}, so appending a phantom pair")
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

        boards = list(
            cls.make_boards(
                boards_per_round_per_table=boards_per_round_per_table,
                num_tables=num_tables,
                tournament=tournament,
            )
        )

        temp_rv: dict[int, list[PlayersAndBoardsForOneRound]] = collections.defaultdict(list)
        for table_number, round_number in itertools.product(range(1, num_tables + 1), repeat=2):
            q = Quartet(
                ns=ns(table_number=table_number, round_number=round_number),
                ew=ew(table_number=table_number, round_number=round_number),
            )

            temp_rv[table_number - 1].append(
                PlayersAndBoardsForOneRound(quartet=q, board_group=boards[round_number - 1].group)
            )
        return cls(
            boards_per_round_per_table=boards_per_round_per_table,
            table_settings_by_table_number=temp_rv,
        )
