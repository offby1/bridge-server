import collections
import datetime
from typing import Generator

from freezegun import freeze_time
import more_itertools
import pytest
import tabulate

from django.contrib import auth

from app.models import Hand, Player, Tournament
from app.models.tournament import _do_signup_expired_stuff
from app.utils.movements import BoardGroup, Movement, Pair, PlayersAndBoardsForOneRound

from .testutils import play_out_hand


def example_pairs(n: int) -> Generator[Pair]:
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
        yield Pair(names=name, id_=frozenset([2 * index, 2 * index + 1]))


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
            rounds: list[PlayersAndBoardsForOneRound]
            for table_number, rounds in enumerate(da_movement.table_settings_by_table_number):
                for r in rounds:
                    quartet, board_group = r.quartet, r.board_group
                    phantoms, normals = quartet.partition_into_phantoms_and_normals()
                    if phantoms:
                        assert len(normals) == 1
                        assert len(phantoms) == 1
                    else:
                        assert len(normals) == 2

            # Ensure every pair plays every board exactly once.
            times_played_by_pair_board_combo: dict[tuple[tuple[int, int], BoardGroup], int] = (
                collections.defaultdict(int)
            )
            for table_number, rounds in enumerate(da_movement.table_settings_by_table_number):
                for r in rounds:
                    quartet, board_group = r.quartet, r.board_group

                    times_played_by_pair_board_combo[(quartet.ns.id_, board_group)] += 1
                    times_played_by_pair_board_combo[(quartet.ew.id_, board_group)] += 1

            assert set(times_played_by_pair_board_combo.values()) == {1}

            # Ensure every NS pair encounters every EW pair exactly once, and vice-versa.
            matchups = collections.Counter()  # type: ignore
            for table_number, rounds in enumerate(da_movement.table_settings_by_table_number):
                for r in rounds:
                    matchups[r.quartet] += 1

            assert matchups.most_common(1)[0][1] == 1

            if (num_pairs, boards_per_round) == (4, 2):
                rows = da_movement.tabulate_me()["rows"]
                import pprint

                pprint.pprint(rows)
                assert rows == [
                    ["1", "NS 1/EW 1 plays board group A", "NS 1/EW 2 plays board group B"],
                    ["2", "NS 2/EW 2 plays board group A", "NS 2/EW 1 plays board group B"],
                ]


def dump_seats() -> list[list[str]]:
    tabulate_me = []
    h: Hand
    for h in Hand.objects.order_by("table_display_number").all():
        if h.is_complete:
            continue
        row = [f"Table # {h.table_display_number}:"]
        for letter, p in h.players_by_direction_letter.items():
            row.append(f"{letter}: {p.name}")
        tabulate_me.append(row)
    print(tabulate.tabulate(tabulate_me))
    return tabulate_me


def test_pairs_and_boards_move(db, everybodys_password) -> None:
    # build up the simplest possible tournament that has more than one round.
    for name in ["n1", "s1", "n2", "s2", "e1", "w1", "e2", "w2"]:
        Player.objects.create(
            user=auth.models.User.objects.create(username=name, password=everybodys_password),
        )

    Player.objects.get_by_name("n1").partner_with(Player.objects.get_by_name("s1"))
    Player.objects.get_by_name("n2").partner_with(Player.objects.get_by_name("s2"))
    Player.objects.get_by_name("e1").partner_with(Player.objects.get_by_name("w1"))
    Player.objects.get_by_name("e2").partner_with(Player.objects.get_by_name("w2"))

    with freeze_time(datetime.datetime(2000, 1, 1)):
        open_tournament, _ = Tournament.objects.get_or_create_tournament_open_for_signups(
            boards_per_round_per_table=1
        )

        for n in ("n1", "n2", "e1", "e2"):
            open_tournament.sign_up_player_and_partner(Player.objects.get_by_name(n))

    with freeze_time(open_tournament.signup_deadline + datetime.timedelta(seconds=1)):
        _do_signup_expired_stuff(open_tournament)
        assert open_tournament.hands().exists()

        num_completed_rounds, _ = open_tournament.rounds_played()
        assert num_completed_rounds == 0, "We haven't played any hands, so this should be round 0"

        before = dump_seats()
        assert before == [
            ["Table # 1:", "N: n1", "E: e1", "S: s1", "W: w1"],
            ["Table # 2:", "N: n2", "E: e2", "S: s2", "W: w2"],
        ]
        for hand in open_tournament.hands().all():
            play_out_hand(hand)

        num_completed_rounds, _ = open_tournament.rounds_played()
        assert (
            num_completed_rounds == 1
        ), "We have played exactly one hand at each table, and advanced to the next round, so this should be round 1"

        after = dump_seats()
        assert after == [
            ["Table # 1:", "N: n1", "E: e2", "S: s1", "W: w2"],
            ["Table # 2:", "N: n2", "E: e1", "S: s2", "W: w1"],
        ]
