import pytest
from app.models import Board, NoMoreBoards, Player, Table
from app.views.hand import _display_and_control
from bridge.card import Card, Suit
from bridge.contract import Bid
from bridge.seat import Seat as libSeat

from .testutils import play_out_hand, set_auction_to


# Who can see which cards (and when)?
# our function under test should look like
def can_see_cards_at(player: Player | None, board: Board, direction: libSeat) -> bool:
    return True


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


def test_completed_tournament(nearly_completed_tournament) -> None:
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

    non_tournament_player = Player.objects.create_synthetic()

    # ok now try various flavors of player
    for player in [None, table.tournament.seated_players().first(), non_tournament_player]:
        for board in table.tournament.board_set.all():
            for direction in libSeat:
                assert can_see_cards_at(
                    None, board, direction
                ), f"Uh, {player} can't see {board} at {direction}?!"


def expect_visibility(expectation_array, table: Table) -> None:
    __tracebackhide__ = True

    for seat in table.current_hand.players_by_direction:
        for viewer in table.current_hand.players_by_direction:
            actual1 = _display_and_control(
                hand=table.current_hand,
                seat=libSeat(seat),
                as_viewed_by=table.current_hand.players_by_direction[viewer],
                as_dealt=False,
            )
            seat_index = "NESW".index(seat)
            viewer_index = "NESW".index(viewer)
            if actual1["display_cards"] != expectation_array[seat_index][viewer_index]:
                pytest.fail(
                    f"{table.current_hand.players_by_direction[viewer]} {'can' if actual1['display_cards'] else 'can not'} see {libSeat(seat)} but {'should not' if actual1['display_cards'] else 'should'}",
                )


@pytest.mark.xfail(reason="WIP")
def test_hand_visibility_one(usual_setup: None) -> None:
    t1 = Table.objects.first()
    assert t1 is not None
    set_auction_to(Bid(level=1, denomination=Suit.CLUBS), t1.current_hand)

    assert str(t1.current_auction.status) == "one Club played by Jeremy Northam, sitting North"

    expect_visibility(
        [
            # n, e, s, w <-- viewers
            [1, 0, 0, 0],  # n seat
            [0, 1, 0, 0],  # e  |
            [0, 0, 1, 0],  # s  |
            [0, 0, 0, 1],  # w  v
        ],
        table=t1,
    )

    # Make the opening lead
    t1.current_hand.add_play_from_player(
        player=t1.current_hand.players_by_direction[libSeat.EAST.value].libraryThing(),
        card=Card.deserialize("D2"),
    )

    # Now the dummy (south) is visible
    expect_visibility(
        [
            # n, e, s, w <-- viewers
            [1, 0, 0, 0],  # n seat
            [0, 1, 0, 0],  # e  |
            [1, 1, 1, 1],  # s  |
            [0, 0, 0, 1],  # w  v
        ],
        table=t1,
    )


def test_hand_visibility_two(two_boards_one_is_complete: None) -> None:
    t2: Table | None = Table.objects.first()
    assert t2 is not None

    expect_visibility(
        [
            # n, e, s, w <-- viewers
            [1, 1, 1, 1],  # n seat
            [1, 1, 1, 1],  # e  |
            [1, 1, 1, 1],  # s  |
            [1, 1, 1, 1],  # w  v
        ],
        table=t2,
    )
