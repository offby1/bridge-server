from __future__ import annotations

import collections
from collections.abc import Generator
import dataclasses
import itertools
import logging
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

import more_itertools

from app.models.types import PK

if TYPE_CHECKING:
    from app.models import Board, Tournament


logger = logging.getLogger(__name__)


@dataclasses.dataclass(order=True)
class Pair:
    id_: tuple[PK, PK]
    names: str

    def __init__(self, *, id_, names):
        self.id_ = tuple(sorted(id_))
        self.names = names

    def __hash__(self) -> int:
        return hash(tuple([self.id_, self.names]))


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
        assert len(self.boards) > 0
        assert _are_consecutive([b.display_number for b in self.boards])
        assert all(b.group == self.letter for b in self.boards)


@dataclasses.dataclass(frozen=True)
class Quartet:
    ns: Pair
    ew: Pair

    # Only used for tests
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

    def __str__(self) -> str:
        return self.names()

    __repr__ = __str__


@dataclasses.dataclass(frozen=True)
class PlayersAndBoardsForOneRound:
    board_group: BoardGroup
    quartet: Quartet
    zb_round_number: int
    table_number: int


def _group_letter(zb_round_number: int) -> str:
    return "ABCDEFGHIJKLMNOP"[zb_round_number]


def _zb_round_number(group_letter: str) -> int:
    return "ABCDEFGHIJKLMNOP".index(group_letter)


@dataclasses.dataclass(frozen=True)
class Movement:
    boards_per_round_per_table: int  # redundant, but handy
    pairs: list[Pair]  # also redundant
    # The number of tables always equals the number of rounds.
    table_settings_by_table_number: tuple[list[PlayersAndBoardsForOneRound], ...]
    num_phantoms: int = 0

    def players_and_boards_for(
        self, *, zb_round_number: int, zb_table_number: int
    ) -> PlayersAndBoardsForOneRound:
        return self.table_settings_by_table_number[zb_table_number][zb_round_number]

    @property
    def total_hands(self) -> int:
        return (
            self.num_rounds
            * len(self.table_settings_by_table_number)
            * self.boards_per_round_per_table
        )

    @property
    def num_rounds(self) -> int:
        return len(self.table_settings_by_table_number)

    def tabulate_me(self) -> dict[str, Any]:
        rows: list[list[str]] = []
        headers = ["table"]
        for tn, rounds in enumerate(self.table_settings_by_table_number):
            if not rows:
                headers.extend(list(f"round {r.zb_round_number + 1}" for r in rounds))
            row = [str(rounds[0].table_number)]

            for r in rounds:
                quartet, board_group = r.quartet, r.board_group
                row.append(f"{quartet.names()} plays board group {board_group.letter}")
            rows.append(row)
        return {"rows": rows, "headers": headers}

    # a "round" is a period where players and boards stay where they are (i.e., at a given table).
    # *within* a round, we play boards_per_round_per_table boards (per table!).

    @staticmethod
    def num_tables(*, num_pairs: int) -> tuple[int, bool]:
        rv, overflow = divmod(num_pairs, 2)
        if rv == 0:
            logger.warning(f"Hmm, {num_pairs=} so of course {rv=}")
        if overflow:
            rv += 1
        return rv, overflow > 0

    @staticmethod
    def ensure_boards(
        *, boards_per_round_per_table: int, num_tables: int, tournament: Tournament
    ) -> Generator[Board]:
        from app.models import Board

        for group_index, display_numbers in enumerate(
            more_itertools.chunked(
                range(1, boards_per_round_per_table * num_tables + 1),
                boards_per_round_per_table,
            )
        ):
            new = old = 0

            for n in display_numbers:
                a_board, created = Board.objects.get_or_create_from_display_number(
                    group=_group_letter(group_index), display_number=n, tournament=tournament
                )
                yield a_board
                if created:
                    new += 1
                else:
                    old += 1

            logger.info(
                f"Created {new} new, and fetched {old} existing, boards for {group_index=} {display_numbers=}"
            )

    @classmethod
    def from_pairs(
        cls,
        *,
        boards_per_round_per_table: int,
        pairs: Sequence[Pair],
        tournament: Tournament,
    ) -> Movement:
        num_phantoms = 0
        num_tables, overflow = cls.num_tables(num_pairs=len(pairs))

        # Sort so that if we later construct movement with the same pairs, albeit perhaps a different order, we get
        # *exactly* the same movement back.
        # In practice our callers already sort, but ... it probably can't hurt to be sure.
        pairs = sorted(pairs)

        if overflow:
            logger.debug(f"{pairs=}; {num_tables=} but {overflow=}, so appending a phantom pair")
            pairs.append(PhantomPair(names="The Fabulous Phantoms", id_=frozenset({-1, -2})))
            num_phantoms += 1

        ns_pairs = pairs[0:num_tables]
        ew_pairs = pairs[num_tables:]

        def ns(*, table_number: int) -> Pair:
            assert 0 < table_number <= num_tables, f"{table_number=} {num_tables=}"
            # Standard Mitchell movement: the NS pair at each table stays put
            return ns_pairs[table_number - 1]

        def ew(*, table_number: int, zb_round_number: int) -> Pair:
            assert 0 < table_number <= num_tables, f"{table_number=} {num_tables=}"
            assert 0 <= zb_round_number < num_tables, f"{zb_round_number=} {num_tables=}"

            # Standard Mitchell movement: the EW pair at each table "rotates" each round
            return ew_pairs[(table_number - 1 - zb_round_number) % num_tables]

        boards_by_group = collections.defaultdict(list)
        for b in cls.ensure_boards(
            boards_per_round_per_table=boards_per_round_per_table,
            num_tables=num_tables,
            tournament=tournament,
        ):
            boards_by_group[b.group].append(b)

        logger.info(
            "Ensured we have %d board groups for tournament #%s (%d boards_per_round_per_table)",
            len(boards_by_group),
            tournament.display_number,
            boards_per_round_per_table,
        )

        temp_rv: dict[int, list[PlayersAndBoardsForOneRound]] = collections.defaultdict(list)

        for table_display_number, displayed_round_number in itertools.product(
            range(1, num_tables + 1), repeat=2
        ):
            zb_round_number = displayed_round_number - 1
            q = Quartet(
                ns=ns(table_number=table_display_number),
                ew=ew(table_number=table_display_number, zb_round_number=zb_round_number),
            )

            letter = _group_letter(zb_round_number)

            assert (
                letter in boards_by_group
            ), f"OK, how come {letter=} isn't a key of {boards_by_group=}"

            temp_rv[table_display_number - 1].append(
                PlayersAndBoardsForOneRound(
                    board_group=BoardGroup(
                        boards=tuple(boards_by_group[letter]),
                        letter=letter,
                    ),
                    quartet=q,
                    zb_round_number=zb_round_number,
                    table_number=table_display_number,
                )
            )

        return cls(
            boards_per_round_per_table=boards_per_round_per_table,
            num_phantoms=num_phantoms,
            pairs=pairs,
            table_settings_by_table_number=tuple([v for k, v in sorted(temp_rv.items())]),
        )
