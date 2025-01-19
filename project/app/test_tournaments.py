from app.models import Tournament

# mumble import settings, monkeypatch, change BOARDS_PER_TOURNAMENT to 2 for convenience


def test_initial_setup_has_no_more_than_one_incomplete_tournament(usual_setup) -> None:
    assert Tournament.objects.filter(is_complete=False).count() < 2


def test_tournament_is_complete_if_and_only_if_all_boards_have_been_played_at_all_tables(
    usual_setup,
) -> None: ...


def test_completing_one_tournament_causes_a_new_one_to_magically_appear(usual_setup) -> None: ...
