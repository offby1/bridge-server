import datetime
import logging

import pytest
from django.core.cache import cache
from django.core.management import call_command
from django.utils import timezone
from pytest_django import Settings

from .models import Hand, Play, Player, Tournament, TournamentSignup
from .models.tournament import advance_expired_tournaments
from .testutils import play_out_round

logger = logging.getLogger(__name__)


@pytest.fixture(autouse=True, scope="function")
def no_ssl_redirect(settings: Settings) -> None:
    settings.SECURE_SSL_REDIRECT = False


@pytest.fixture(autouse=True, scope="function")
def clear_django_cache(settings: Settings):
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "unit-tests",
        }
    }
    cache.clear()


# Without this, a couple tests fail *unless* you happen to have run "collectstatic" first.
@pytest.fixture(autouse=True)
def shaddap_complaints_about_missing_staticfiles_manifest_entries(settings: Settings):
    # https://docs.djangoproject.com/en/dev/ref/contrib/staticfiles/#django.contrib.staticfiles.storage.ManifestStaticFilesStorage.manifest_strict
    settings.STORAGES["staticfiles"]["BACKEND"] = (
        "django.contrib.staticfiles.storage.StaticFilesStorage"
    )


@pytest.fixture(scope="session", autouse=True)
def everybodys_password() -> str:
    return (
        # In [1]: from django.contrib.auth.hashers import make_password
        # In [2]: make_password(".")
        # Out[2]: 'pbkdf2_sha256$870000$2hIscex1sYiQd86rzIuNEb$C1t3fgjQJ00VLQA6H7Hg25GGjkyLc9CBfkzNTSbqYTU='
        "pbkdf2_sha256$870000$2hIscex1sYiQd86rzIuNEb$C1t3fgjQJ00VLQA6H7Hg25GGjkyLc9CBfkzNTSbqYTU="
    )


# Just to prevent tests from displaying the actual secret key if they fail
@pytest.fixture(autouse=True)
def innocuous_secret_key(settings: Settings):
    settings.SECRET_KEY = "gabba gabba hey"


@pytest.fixture
def usual_setup(db: None) -> Hand:
    call_command("loaddata", "usual_setup")

    h = Hand.objects.first()
    assert h is not None
    return h


@pytest.fixture
def nobody_seated_nobody_signed_up(db: None) -> None:
    call_command(
        "loaddata",
        "fresh_tournament",
    )
    TournamentSignup.objects.all().delete()


@pytest.fixture
def nobody_seated(nobody_seated_nobody_signed_up: None) -> None:
    """One tournament, open for signups, with everybody signed up to it.

    Reopen the tournament `nobody_seated_nobody_signed_up` loaded, rather than calling
    `get_or_create_tournament_open_for_signups()` and letting it create a second one:
    the loaded tournament's signup deadline is in 1970, so it would not qualify. Leaving
    two behind means a test asking for "the tournament" gets an ambiguous answer, and
    `Tournament.objects.first()` gets the empty one.
    """
    Tournament.objects.update(signup_deadline=timezone.now() + datetime.timedelta(seconds=300))

    tournament = Tournament.objects.get()
    for p in Player.objects.all():
        tournament.sign_up_player_and_partner(p)


@pytest.fixture
def two_boards_one_of_which_is_played_almost_to_completion(db: None) -> None:
    call_command("loaddata", "two_boards_one_of_which_is_played_almost_to_completion")


@pytest.fixture
def fresh_tournament(db: None) -> Tournament:
    call_command("loaddata", "fresh_tournament")
    t = Tournament.objects.first()
    assert t is not None
    return t


@pytest.fixture
def nearly_completed_tournament(db: None) -> Tournament:
    call_command("loaddata", "nearly_completed_tournament")
    t = Tournament.objects.first()
    assert t is not None
    return t


@pytest.fixture
def two_boards_one_is_complete(
    two_boards_one_of_which_is_played_almost_to_completion: None,
) -> Hand:
    h1 = Hand.objects.get(pk=1)
    Play.objects.create(hand=h1, serialized="♠A")
    advance_expired_tournaments()

    return h1


@pytest.fixture
def just_completed(two_boards_one_of_which_is_played_almost_to_completion: None) -> Tournament:
    before: Tournament | None = Tournament.objects.incompletes().first()
    assert before is not None

    play_out_round(before)
    return before
