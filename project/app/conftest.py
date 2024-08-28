import bridge.seat
import pytest
from django.contrib import auth

from .models import Player, Seat, Table


@pytest.fixture
def usual_setup(db):
    directions_by_player_name = dict([
        ("Bob", bridge.seat.Seat.NORTH),
        ("Carol", bridge.seat.Seat.EAST),
        ("Ted", bridge.seat.Seat.SOUTH),
        ("Alice", bridge.seat.Seat.WEST),
    ])

    for name in directions_by_player_name:
        Player.objects.create(
            user=auth.models.User.objects.create_user(username=name, password=name)
        )

    Player.objects.get_by_name("Ted").partner_with(Player.objects.get_by_name("Bob"))
    Player.objects.get_by_name("Alice").partner_with(Player.objects.get_by_name("Carol"))

    Table.objects.create_with_two_partnerships(
        p1=Player.objects.get_by_name("Ted"), p2=Player.objects.get_by_name("Alice")
    )
