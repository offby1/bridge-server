from .models import Tournament


def test_tournament_players(just_completed: Tournament) -> None:
    assert set(just_completed.players().values_list("pk", flat=True)) == {1, 2, 3, 4}


def test_scoring(just_completed: Tournament) -> None:
    assert just_completed.is_complete

    scores_by_player_pk = {
        player.pk: just_completed.score_for_partnership(one_player=player)
        for player in just_completed.players()
    }

    values = set(list(scores_by_player_pk.values()))

    assert len(values) > 1
