import bridge.seat
import pytest
from django.contrib import auth

from .models import Player, Seat, Table


@pytest.fixture
def usual_setup(db):
    t = Table.objects.create()

    directions_by_player_name = dict([
        ("Bob", bridge.seat.Seat.NORTH),
        ("Carol", bridge.seat.Seat.EAST),
        ("Ted", bridge.seat.Seat.SOUTH),
        ("Alice", bridge.seat.Seat.WEST),
    ])

    for name in directions_by_player_name:
        u = auth.models.User.objects.create_user(username=name, password=name)
        p = Player.objects.create(user=u)

    Player.objects.get_by_name("Ted").partner_with(Player.objects.get_by_name("Bob"))
    Player.objects.get_by_name("Alice").partner_with(Player.objects.get_by_name("Carol"))

    for name, direction in directions_by_player_name.items():
        p = Player.objects.get_by_name(name)
        Seat.objects.create(direction=direction.value, player=p, table=t)
