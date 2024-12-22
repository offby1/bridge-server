import pytest
from django.contrib import auth
from django.core.management import call_command

from .models import Board, Hand, Play, Player, Table, Tournament
from .models.board import board_attributes_from_board_number


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


# Just to prevent tests from displaying the actual secret key if they fail
@pytest.fixture(autouse=True)
def innocuous_secret_key(settings):
    settings.SECRET_KEY = "gabba gabba hey"


@pytest.fixture
def usual_setup(db: None) -> None:
    call_command("loaddata", "usual_setup")


@pytest.fixture
def played_almost_to_completion(db: None) -> None:
    call_command("loaddata", "played_almost_to_completion")


@pytest.fixture
def played_to_completion(played_almost_to_completion) -> None:
    h1 = Hand.objects.get(pk=1)
    Play.objects.create(hand=h1, serialized="♠A")


@pytest.fixture
def second_setup(usual_setup):
    new_player_names = ["n2", "e2", "s2", "w2"]
    for name in new_player_names:
        Player.objects.create(
            user=auth.models.User.objects.create(username=name, password=everybodys_password),
        )

    Player.objects.get_by_name("n2").partner_with(Player.objects.get_by_name("s2"))
    Player.objects.get_by_name("e2").partner_with(Player.objects.get_by_name("w2"))
    Board.objects.create_from_attributes(
        attributes=board_attributes_from_board_number(board_number=2, rng_seeds=[]),
        tournament=Tournament.objects.first(),
    )

    return Table.objects.create_with_two_partnerships(
        p1=Player.objects.get_by_name("n2"),
        p2=Player.objects.get_by_name("e2"),
    )
