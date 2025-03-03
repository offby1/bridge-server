import logging

import pytest
from django.contrib import auth
from django.core.cache import cache
from django.core.management import call_command

from .models import Hand, Play, Player, Table, Tournament, TournamentSignup
from .models.tournament import check_for_expirations


logger = logging.getLogger(__name__)


@pytest.fixture(autouse=True)
def dump_django_cache():
    cache.clear()


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
def nobody_seated(db: None) -> None:
    call_command(
        "loaddata",
        "usual_setup",
        "--exclude",
        "app.seat",
        "--exclude",
        "app.hand",
        "--exclude",
        "app.table",
    )
    Player.objects.all().update(currently_seated=False)
    for p in Player.objects.all():
        for b in p.boards_played.all():
            p.boards_played.remove(b)


@pytest.fixture
def two_boards_one_of_which_is_played_almost_to_completion(db: None) -> None:
    call_command("loaddata", "two_boards_one_of_which_is_played_almost_to_completion")


@pytest.fixture
def fresh_tournament(db: None) -> None:
    call_command("loaddata", "fresh_tournament")


@pytest.fixture
def nearly_completed_tournament(db: None) -> None:
    call_command("loaddata", "nearly_completed_tournament")


@pytest.fixture
def two_boards_one_is_complete(two_boards_one_of_which_is_played_almost_to_completion) -> None:
    h1 = Hand.objects.get(pk=1)
    Play.objects.create(hand=h1, serialized="♠A")
    check_for_expirations(__name__)


@pytest.fixture
def second_setup(usual_setup):
    new_player_names = ["n2", "e2", "s2", "w2"]
    for name in new_player_names:
        Player.objects.create(
            user=auth.models.User.objects.create(username=name, password=everybodys_password),
        )

    Player.objects.get_by_name("n2").partner_with(Player.objects.get_by_name("s2"))
    Player.objects.get_by_name("e2").partner_with(Player.objects.get_by_name("w2"))

    table = Table.objects.create_with_two_partnerships(
        p1=Player.objects.get_by_name("n2"),
        p2=Player.objects.get_by_name("e2"),
        tournament=Tournament.objects.first(),
    )
    table.next_board()
    return table
