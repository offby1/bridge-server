import pytest

from django.core.management import call_command
from .models import Tournament


@pytest.fixture
def two_by_two(db: None) -> Tournament:
    call_command("loaddata", "two_by_two_all_tied")
    rv = Tournament.objects.first()
    assert rv is not None
    return rv


def test_tournament_players(two_by_two: Tournament) -> None:
    assert set(two_by_two.players().values_list("pk", flat=True)) == {1, 2, 3, 4, 5, 6, 7, 8}


def test_scoring_two_by_two(two_by_two: Tournament) -> None:
    assert two_by_two.is_complete

    actual = two_by_two.matchpoints_by_pair_by_board()

    expected = {
        "n/s": {
            1: {"_prez/_rhonda": 2, "_bodie/_kima": 0},
            2: {"_prez/_rhonda": 1, "_bodie/_kima": 1},
        },
        "e/w": {
            1: {"_tony gray/_sydnor": 0, "_randy/_marla": 2},
            2: {"_randy/_marla": 1, "_tony gray/_sydnor": 1},
        },
    }

    assert actual == expected
