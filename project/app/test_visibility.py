import datetime

import freezegun
import pytest

from app.models import Board, Hand, NoMoreBoards, Player, Table, Tournament
from app.models.tournament import check_for_expirations
from bridge.card import Suit
from bridge.contract import Bid
from bridge.seat import Seat as libSeat

from .testutils import play_out_hand, set_auction_to


# Who can see which cards (and when)?

# a "None" player means the anonymous user.
# cases to check:
# (no need to check, just a reminder): if the tournament is still in signup mode, there *are* no boards
# - if the tournament is complete, everyone can see everything.
# - otherwise the tournament is running, and ...
#   - if player is None, they can see nothing, since otherwise a player could get a new browser window, peek at the hand they're currently playing, and cheat up the yin-yang
#   - if it's a Player, and they are not signed up for this tournament: they can see nothing, since again it'd be too easy to cheat (just sign up a new username)
#   - if it's a Player, and they are in this tournament:
#     - if they have not yet played this board, nope
#     - if they have been seated at a hand with this board:
#       - if it's their own cards, of course they can see them
#       - if the opening lead has been played, they can also see the dummy
#       - if the hand is complete (either passed out, or all 13 tricks played), they can also see their opponent's cards (i.e., everything)


def can_see_cards_at(player: Player | None, board: Board, direction: libSeat) -> bool:
    print(f"can_see_cards_at: {getattr(player, 'name', 'Noah Buddy')=} {board=} {direction.value=}")
    if board.tournament.is_complete:
        print(f"{board.tournament.is_complete=} so everyone can see everything")
        return True

    if player is not None:
        if (hand := player.hand_at_which_board_was_played(board)) is not None:
            if hand.get_xscript().final_score() is not None:
                return True

            for d, p in hand.players_by_direction.items():
                # everyone gets to see their own cards
                if p == player and d == direction.value:
                    print(
                        f"{p.name=} == {player.name=} and {d=} == {direction.value=}: player can see own hand"
                    )
                    return True

                # Dummy is visible after the opening lead
                if (
                    hand.get_xscript().num_plays > 0
                    and hand.dummy.seat.value == d == direction.value
                ):
                    print(f"{hand.dummy.seat.value=} and {d=}; everyone can see the dummy")
                    return True
    return False


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
                assert can_see_cards_at(
                    player,
                    board,
                    direction,
                ), f"Uh, {player} can't see {board} at {direction}?!"


def test_running_tournament_irrelevant_players(nearly_completed_tournament) -> None:
    table: Table | None = Table.objects.first()
    assert table is not None

    non_tournament_player = Player.objects.create_synthetic()

    for player in [None, non_tournament_player]:
        for board in table.tournament.board_set.all():
            for direction in libSeat:
                assert not can_see_cards_at(
                    player,
                    board,
                    direction,
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
                    assert not can_see_cards_at(
                        player,
                        board,
                        direction,
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

            for direction in libSeat:
                for p, d in hand.players_by_direction.items():
                    if p == player:
                        assert can_see_cards_at(
                            p,
                            board,
                            direction,
                        ), f"Hey now -- {player} can't see their own cards ({board} at {direction})?!"


def test_zero_cards_played(fresh_tournament) -> None:
    Today = datetime.datetime.fromisoformat("2012-01-10T00:00:00Z")
    Tomorrow = Today + datetime.timedelta(seconds=3600 * 24)

    the_tournament: Tournament = Tournament.objects.first()
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

    the_tournament: Tournament = Tournament.objects.first()
    assert the_tournament is not None
    the_tournament.play_completion_deadline = Tomorrow
    the_tournament.save()

    with freezegun.freeze_time(Today):
        check_for_expirations(__name__)
        table: Table | None = Table.objects.first()
        assert table is not None

        set_auction_to(Bid(level=1, denomination=Suit.CLUBS), table.current_hand)

        h: Hand = table.current_hand
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

    the_tournament: Tournament = Tournament.objects.first()
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
            actual = can_see_cards_at(
                player=viewer, board=table.current_hand.board, direction=seat.libraryThing
            )
            seat_index = "NESW".index(seat.direction)
            if actual != expectation_array[seat_index][viewer_index]:
                print(f"{actual=} {seat=} {seat_index=} {viewer.name=} {viewer_index=}")
                pytest.fail(
                    f"{viewer} {'can' if actual else 'can not'} see {seat.direction} but {'should not' if actual else 'should'}",
                )
