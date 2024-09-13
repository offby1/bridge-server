import pytest
from bridge.seat import Seat
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
    player_names_by_direction = {
        Seat.NORTH: "Jeremy Northam",
        Seat.EAST: "Clint Eastwood",
        Seat.SOUTH: "J.D. Souther",
        Seat.WEST: "Adam West",
    }

    for name in player_names_by_direction.values():
        Player.objects.create(
            user=auth.models.User.objects.create(username=name, password=everybodys_password),
        )

    Player.objects.get_by_name(player_names_by_direction[Seat.NORTH]).partner_with(
        Player.objects.get_by_name(player_names_by_direction[Seat.SOUTH])
    )
    Player.objects.get_by_name(player_names_by_direction[Seat.EAST]).partner_with(
        Player.objects.get_by_name(player_names_by_direction[Seat.WEST])
    )

    Table.objects.create_with_two_partnerships(
        p1=Player.objects.get_by_name(player_names_by_direction[Seat.NORTH]),
        p2=Player.objects.get_by_name(player_names_by_direction[Seat.EAST]),
        shuffle_deck=False,
    )
