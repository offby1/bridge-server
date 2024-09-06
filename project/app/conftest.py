import bridge.seat
import pytest
from django.contrib import auth

from .models import Player, Table


@pytest.fixture(scope="session", autouse=True)
def everybodys_password():
    return (
        # In [1]: from django.contrib.auth.hashers import make_password
        # In [2]: make_password(".")
        # Out[2]: 'pbkdf2_sha256$870000$2hIscex1sYiQd86rzIuNEb$C1t3fgjQJ00VLQA6H7Hg25GGjkyLc9CBfkzNTSbqYTU='
        "pbkdf2_sha256$870000$2hIscex1sYiQd86rzIuNEb$C1t3fgjQJ00VLQA6H7Hg25GGjkyLc9CBfkzNTSbqYTU="
    )


@pytest.fixture
def usual_setup(db, everybodys_password):
    directions_by_player_name = {
        "Ted": bridge.seat.Seat.NORTH,
        "Alice": bridge.seat.Seat.EAST,
        "Bob": bridge.seat.Seat.SOUTH,
        "Carol": bridge.seat.Seat.WEST,
    }

    for name in directions_by_player_name:
        Player.objects.create(
            user=auth.models.User.objects.create(username=name, password=everybodys_password),
        )

    Player.objects.get_by_name("Ted").partner_with(Player.objects.get_by_name("Bob"))
    Player.objects.get_by_name("Alice").partner_with(Player.objects.get_by_name("Carol"))

    Table.objects.create_with_two_partnerships(
        p1=Player.objects.get_by_name("Ted"),
        p2=Player.objects.get_by_name("Alice"),
    )
