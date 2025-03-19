from __future__ import annotations

import collections
from collections.abc import Generator
import dataclasses
import itertools
import logging
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

import more_itertools
import tabulate

from app.models.common import SEAT_CHOICES
from app.models.types import PK

if TYPE_CHECKING:
    from app.models import Board, Tournament


logger = logging.getLogger(__name__)


@dataclasses.dataclass(order=True)
class Pair:
    id_: tuple[PK, PK]
    names: str

    def __init__(self, *, id, names):
        self.id_ = tuple(sorted(id))
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


@dataclasses.dataclass(frozen=True)
class Movement:
    boards_per_round_per_table: int  # redundant, but handy
    # The number of tables always equals the number of rounds.
    table_settings_by_table_number: dict[int, list[PlayersAndBoardsForOneRound]]

    def __post_init__(self):
        tab_dict = self.tabulate_me()
        print()
        print(tabulate.tabulate(tab_dict["rows"], headers=tab_dict["headers"]))

    def tabulate_me(self) -> dict[str, Any]:
        rows: list[list[str]] = []
        headers = ["table"]
        for tn, rounds in self.table_settings_by_table_number.items():
            if not rows:
                headers.extend(list(f"round {r.zb_round_number + 1}" for r in rounds))
            row = [str(rounds[0].table_number)]

            for r in rounds:
                quartet, board_group = r.quartet, r.board_group
                row.append(f"{quartet.names()} plays board group {board_group.letter}")
            rows.append(row)
        return {"rows": rows, "headers": headers}

    def allocate_initial_tables(self, tournament) -> None:
        from app.models import Table

        logger.warning(
            "%s", f"{tournament.display_number=} {self.table_settings_by_table_number.keys()=}"
        )
        for tn, table_settings in sorted(self.table_settings_by_table_number.items()):
            Table.objects.create(tournament=tournament)
        for t in Table.objects.all():
            logger.warning("%s", f"{t.tournament.display_number=}: {t.display_number=}")

    # a "round" is a period where players and boards stay where they are (i.e., at a given table).
    # *within* a round, we play boards_per_round_per_table boards (per table!).

    # TODO -- it kinda feels like this method, which is all about side effects, should live in the Tournament class, and
    # not here; *this* class should be functional, and merely provide information about which players and boards go to
    # which tables and when.
    def update_tables_and_seat_players_for_round(
        self, *, tournament: Tournament, zb_round_number: int
    ) -> None:
        logger.debug(
            "Hello world! tournament #%d, round_number #%d",
            tournament.display_number,
            zb_round_number,
        )
        from app.models import Player, Table

        assert 0 <= zb_round_number
        if zb_round_number >= len(self.table_settings_by_table_number[0]):
            from app.models import NoMoreBoards

            msg = f"Tournament #{tournament.display_number} only has {len(self.table_settings_by_table_number[0])} rounds, but you asked for {zb_round_number=}"
            raise NoMoreBoards(msg)

        zb_table_index: int
        table_settings: list[PlayersAndBoardsForOneRound]
        for zb_table_index, table_settings in sorted(self.table_settings_by_table_number.items()):
            ts = table_settings[zb_round_number]
            assert ts.zb_round_number == zb_round_number
            phantom_pairs, normal_pairs = ts.quartet.partition_into_phantoms_and_normals()

            if phantom_pairs:
                assert len(normal_pairs) == 1
                assert len(phantom_pairs) == 1

                # Don't create a table; just inform the normal pair that they're sitting out this round
                for pk in normal_pairs[0].id_:
                    Player.objects.get(pk=pk).unseat_partnership(
                        reason=f"You're sitting out round {zb_round_number + 1}"
                    )
                    break  # we only need to unseat one of the two partners
                continue

            pair1, pair2 = normal_pairs

            assert (
                len(set(pair1.id_ + pair2.id_)) == 4
            ), f"Hmm, {normal_pairs} isn't exactly four players"
            pk1 = pair1.id_[0]
            pk2 = pair2.id_[0]
            player1 = Player.objects.get(pk=pk1)
            player2 = Player.objects.get(pk=pk2)

            logger.debug("fetching table #%s", zb_table_index + 1)
            table: Table = Table.objects.get(
                tournament=tournament, display_number=zb_table_index + 1
            )

            # Whover's currently at the table gotta make room
            table.unseat_players(
                reason=f"You're about to be reseated for round {zb_round_number + 1}"
            )

            # The new tentants gotta leave their current table
            player1.unseat_partnership()
            player2.unseat_partnership()

            # TODO -- this is a copy of code in TableManager.create_with_two_partnerships
            from app.models import Seat

            for seat, player in zip(
                SEAT_CHOICES, (player1, player2, player1.partner, player2.partner)
            ):
                Seat.objects.create(
                    direction=seat,
                    player=player,
                    table=table,
                )

            table.next_board()

            logger.debug(
                f"{zb_table_index=} {zb_round_number=} {table_settings[zb_round_number]=} updated seats for {table}"
            )

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
            logger.info("%s", f"Making boards for {group_index=} {display_numbers=}")
            for n in display_numbers:
                a_board, created = Board.objects.get_or_create_from_display_number(
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
        for b in cls.make_boards(
            boards_per_round_per_table=boards_per_round_per_table,
            num_tables=num_tables,
            tournament=tournament,
        ):
            boards_by_group[b.group].append(b)

        logger.info(
            "Made %d board groups for tournament #%s (%d boards_per_round_per_table)",
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
            table_settings_by_table_number=temp_rv,
        )
