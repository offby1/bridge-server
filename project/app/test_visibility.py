import datetime

import freezegun
import pytest

from app.models import Board, Hand, NoMoreBoards, Player, Table, Tournament
from app.models.tournament import check_for_expirations
from bridge.card import Suit
from bridge.contract import Bid
from bridge.seat import Seat as libSeat

from .testutils import play_out_hand, set_auction_to


@pytest.fixture
def completed_tournament(nearly_completed_tournament) -> Table:
    # Complete that tournament!
    table: Table | None = Table.objects.first()
    assert table is not None

    while True:
        play_out_hand(table)
        try:
            table.next_board()
        except NoMoreBoards:
            break

    assert table.tournament.is_complete
    return table


def test_completed_tournament(completed_tournament) -> None:
    table = completed_tournament
    non_tournament_player = Player.objects.create_synthetic()

    # ok now try various flavors of player
    for player in [None, table.tournament.seated_players().first(), non_tournament_player]:
        for board in table.tournament.board_set.all():
            for direction in libSeat:
                assert board.can_see_cards_at(
                    player=player,
                    direction=direction,
                ), f"Uh, {player} can't see {board} at {direction}?!"


def test_running_tournament_irrelevant_players(nearly_completed_tournament) -> None:
    table: Table | None = Table.objects.first()
    assert table is not None

    non_tournament_player = Player.objects.create_synthetic()

    for player in [None, non_tournament_player]:
        for board in table.tournament.board_set.all():
            for direction in libSeat:
                assert not board.can_see_cards_at(
                    player=player,
                    direction=direction,
                ), f"Whoa -- {player} can see {board} at {direction}?!"


def test_running_tournament_relevant_player_not_yet_played_board(
    nearly_completed_tournament,
) -> None:
    table: Table | None = Table.objects.first()
    assert table is not None

    for player in table.tournament.seated_players():
        for board in table.tournament.board_set.all():
            hand = player.hand_at_which_board_was_played(board)
            if hand is None:
                for direction in libSeat:
                    assert not board.can_see_cards_at(
                        player=player,
                        direction=direction,
                    ), f"Whoa -- {player} can see {board} at {direction}?!"


def test_player_has_played_board(
    nearly_completed_tournament,
) -> None:
    table: Table | None = Table.objects.first()
    assert table is not None

    for player in table.tournament.seated_players():
        board: Board
        for board in table.tournament.board_set.all():
            hand: Hand = player.hand_at_which_board_was_played(board)

            if hand is None:
                continue

            for d, p in hand.players_by_direction.items():
                if p == player:
                    assert board.can_see_cards_at(
                        player=p,
                        direction=libSeat(d),
                    ), f"Hey now -- {player} can't see their own cards ({board} at {d})?!"


def test_zero_cards_played(fresh_tournament) -> None:
    Today = datetime.datetime.fromisoformat("2012-01-10T00:00:00Z")
    Tomorrow = Today + datetime.timedelta(seconds=3600 * 24)

    the_tournament: Tournament | None = Tournament.objects.first()
    assert the_tournament is not None
    the_tournament.play_completion_deadline = Tomorrow
    the_tournament.save()

    with freezegun.freeze_time(Today):
        check_for_expirations(__name__)
        table: Table | None = Table.objects.first()
        assert table is not None

        expect_visibility(
            [
                # n, e, s, w <-- viewers
                [1, 0, 0, 0],  # n seat
                [0, 1, 0, 0],  # e  |
                [0, 0, 1, 0],  # s  |
                [0, 0, 0, 1],  # w  v
            ],
            table=table,
        )


def test_one_card_played(fresh_tournament) -> None:
    Today = datetime.datetime.fromisoformat("2012-01-10T00:00:00Z")
    Tomorrow = Today + datetime.timedelta(seconds=3600 * 24)

    the_tournament: Tournament | None = Tournament.objects.first()
    assert the_tournament is not None
    the_tournament.play_completion_deadline = Tomorrow
    the_tournament.save()

    with freezegun.freeze_time(Today):
        check_for_expirations(__name__)
        table: Table | None = Table.objects.first()
        assert table is not None

        set_auction_to(Bid(level=1, denomination=Suit.CLUBS), table.current_hand)

        h: Hand = table.current_hand
        assert h.player_who_may_play is not None
        leader = h.player_who_may_play.libraryThing()
        libCard = h.get_xscript().slightly_less_dumb_play().card

        h.add_play_from_player(player=leader, card=libCard)

        expect_visibility(
            [
                # n, e, s, w <-- viewers
                [1, 0, 0, 0],  # n seat
                [0, 1, 0, 0],  # e  |
                [1, 1, 1, 1],  # s  | (dummy)
                [0, 0, 0, 1],  # w  v
            ],
            table=table,
        )


def test_52_cards_played(fresh_tournament) -> None:
    Today = datetime.datetime.fromisoformat("2012-01-10T00:00:00Z")
    Tomorrow = Today + datetime.timedelta(seconds=3600 * 24)

    the_tournament: Tournament | None = Tournament.objects.first()
    assert the_tournament is not None
    the_tournament.play_completion_deadline = Tomorrow
    the_tournament.save()

    with freezegun.freeze_time(Today):
        check_for_expirations(__name__)
        table: Table | None = Table.objects.first()
        assert table is not None

        play_out_hand(table)

        expect_visibility(
            [
                # n, e, s, w <-- viewers
                [1, 1, 1, 1],  # n seat
                [1, 1, 1, 1],  # e  |
                [1, 1, 1, 1],  # s  | (dummy)
                [1, 1, 1, 1],  # w  v
            ],
            table=table,
        )


def expect_visibility(expectation_array, table: Table) -> None:
    __tracebackhide__ = True

    seats = table.current_seats()

    for seat in seats:
        for viewer_index, viewer in enumerate([s.player for s in seats]):
            actual = table.current_hand.board.can_see_cards_at(
                player=viewer, direction=seat.libraryThing
            )
            seat_index = "NESW".index(seat.direction)
            if actual != expectation_array[seat_index][viewer_index]:
                print(f"{actual=} {seat=} {seat_index=} {viewer.name=} {viewer_index=}")
                pytest.fail(
                    f"{viewer} {'can' if actual else 'can not'} see {seat.direction} but {'should not' if actual else 'should'}",
                )
