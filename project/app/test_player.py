# Tests for the "tainting" mechanism.
import pytest

from app.models import Board, Player, Seat, Table


@pytest.fixture
def seat_em_dano(nobody_seated: None) -> Table:
    north = Player.objects.get_by_name("Jeremy Northam")
    south = Player.objects.get_by_name("J.D. Souther")
    east = Player.objects.get_by_name("Clint Eastwood")
    west = Player.objects.get_by_name("Adam West")

    # Since everything is nice and virgin, we otta be able to seat everyone, dontcha think?
    north.partner_with(south)
    east.partner_with(west)

    # Not calling create_with_two_partnerships since that invokes "next_board", which I'd prefer to invoke explicitly
    t = Table.objects.create()
    Seat.objects.create(direction="N", player=north, table=t)
    Seat.objects.create(direction="E", player=east, table=t)
    Seat.objects.create(direction="S", player=south, table=t)
    Seat.objects.create(direction="W", player=west, table=t)

    return t


def test_untainted_players_may_play_any_board(seat_em_dano) -> None:
    # Just making sure this test isn't out of sync with the fixture
    assert set(Board.objects.values_list("pk", flat=True)) == {1, 2}

    t = seat_em_dano
    t.next_board()
