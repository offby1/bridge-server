# Tests for the "tainting" mechanism.
import importlib

import pytest
from django.conf import settings
from django.contrib import auth

from app.models import Board, Hand, HandError, Player, Seat, Table


@pytest.fixture
def seat_em_dano(nobody_seated: None) -> Table:
    # Just making sure this test isn't out of sync with the fixture
    assert set(Board.objects.values_list("pk", flat=True)) == {1, 2}

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
    t = seat_em_dano
    for b in t.tournament.board_set.all():
        Hand.objects.create(board=b, table=t)

    # We're just checking for the lack of an exception.


def test_tainted_players_may_not_play_relevant_board(seat_em_dano: Table) -> None:
    t = seat_em_dano
    t.tournament.add_boards(n=2)
    board_one, board_two = t.tournament.board_set.all()[0:2]

    north = Player.objects.get_by_name("Jeremy Northam")
    north.taint_board(board_pk=board_one.pk)

    with pytest.raises(HandError) as e:
        Hand.objects.create(board=board_one, table=t)
    assert "Cannot seat" in str(e.value)

    Hand.objects.create(board=board_two, table=t)


def test_player_messages_are_private(usual_setup, everybodys_password) -> None:
    module_name, class_name = settings.EVENTSTREAM_CHANNELMANAGER_CLASS.rsplit(".", maxsplit=1)
    cm = getattr(importlib.import_module(module_name), class_name)()

    north = Player.objects.get_by_name("Jeremy Northam")
    south = Player.objects.get_by_name("J.D. Souther")

    assert cm.can_read_channel(north, north.event_channel_name)
    assert not cm.can_read_channel(north, south.event_channel_name)
    assert cm.can_read_channel(south, south.event_channel_name)
    assert not cm.can_read_channel(south, north.event_channel_name)

    the_hand = Hand.objects.first()
    assert the_hand is not None
    assert north in the_hand.players()
    assert south in the_hand.players()

    assert cm.can_read_channel(north, the_hand.event_channel_name)
    assert cm.can_read_channel(south, the_hand.event_channel_name)

    j_random_user = auth.models.User.objects.create(
        username="J. Random User, Esq", password=everybodys_password
    )

    assert not cm.can_read_channel(j_random_user, the_hand.event_channel_name)
