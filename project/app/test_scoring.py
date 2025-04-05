from .models import Tournament


def test_tournament_players(just_completed: Tournament) -> None:
    assert just_completed.players().count == 4


def test_scoring(just_completed: Tournament) -> None:
    assert just_completed.is_complete

    scores_by_player = {
        player: just_completed.score_for(player=player) for player in just_completed.players()
    }

    assert len(set(scores_by_player.values())) > 0
