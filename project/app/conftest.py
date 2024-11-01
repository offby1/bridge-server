import bridge.card
import pytest
from bridge.seat import Seat
from django.contrib import auth

from .models import Board, Player, Table


# Without this, a couple tests fail *unless* you happen to have run "collectstatic" first.
@pytest.fixture(autouse=True)
def shaddap_complaints_about_missing_staticfiles_manifest_entries(settings):
    # https://docs.djangoproject.com/en/dev/ref/contrib/staticfiles/#django.contrib.staticfiles.storage.ManifestStaticFilesStorage.manifest_strict
    settings.STORAGES["staticfiles"]["BACKEND"] = (
        "django.contrib.staticfiles.storage.StaticFilesStorage"
    )


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

    return Table.objects.create_with_two_partnerships(
        p1=Player.objects.get_by_name(player_names_by_direction[Seat.NORTH]),
        p2=Player.objects.get_by_name(player_names_by_direction[Seat.EAST]),
        shuffle_deck=False,
    )


@pytest.fixture
def second_setup(usual_setup):
    new_player_names = ["n2", "e2", "s2", "w2"]
    for name in new_player_names:
        Player.objects.create(
            user=auth.models.User.objects.create(username=name, password=everybodys_password),
        )

    Player.objects.get_by_name("n2").partner_with(Player.objects.get_by_name("s2"))
    Player.objects.get_by_name("e2").partner_with(Player.objects.get_by_name("w2"))
    Board.objects.create_from_deck(deck=bridge.card.Card.deck())

    return Table.objects.create_with_two_partnerships(
        p1=Player.objects.get_by_name("n2"),
        p2=Player.objects.get_by_name("e2"),
        shuffle_deck=False,
    )
