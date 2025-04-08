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

    actual = two_by_two.matchpoints_by_partnership_by_hand()
    expected = {
        1: {
            1: {"matchpoints": 2, "names": ["_prez", "_rhonda"]},
            5: {"matchpoints": 0, "names": ["_tony gray", "_sydnor"]},
        },
        2: {
            3: {"matchpoints": 0, "names": ["_bodie", "_kima"]},
            7: {"matchpoints": 2, "names": ["_randy", "_marla"]},
        },
        3: {
            1: {"matchpoints": 1, "names": ["_prez", "_rhonda"]},
            7: {"matchpoints": 1, "names": ["_randy", "_marla"]},
        },
        4: {
            3: {"matchpoints": 1, "names": ["_bodie", "_kima"]},
            5: {"matchpoints": 1, "names": ["_tony gray", "_sydnor"]},
        },
    }

    assert actual == expected
