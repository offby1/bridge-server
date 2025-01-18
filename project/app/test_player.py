# Tests for the "tainting" mechanism.

from app.models import Player


def test_tainted_player_may_not_play_that_board(nobody_seated: None) -> None:
    north = Player.objects.get_by_name("Jeremy Northam")
    south = Player.objects.get_by_name("J.D. Souther")
    east = Player.objects.get_by_name("Clint Eastwood")
    west = Player.objects.get_by_name("Adam West")

    # Since everything is nice and virgin, we otta be able to seat everyone, dontcha think?
    north.partner_with(south)
    east.partner_with(west)

    assert north.name == "south"
