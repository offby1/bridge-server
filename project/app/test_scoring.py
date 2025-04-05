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

    matchpoints_by_board_by_player_pk = {
        player.pk: two_by_two.matchpoints_for_partnership_by_board(one_player=player)
        for player in two_by_two.players()
    }

    assert matchpoints_by_board_by_player_pk == {
        1: {1: 2, 2: 1},
        2: {1: 2, 2: 1},
        3: {1: 0, 2: 1},
        4: {1: 0, 2: 1},
        5: {1: 0, 2: 1},
        6: {1: 0, 2: 1},
        7: {1: 2, 2: 1},
        8: {1: 2, 2: 1},
    }
