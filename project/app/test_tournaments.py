import pytest
from bridge.card import Card

import app.views.hand
from app.models import Hand, Player, Tournament

# mumble import settings, monkeypatch, change BOARDS_PER_TOURNAMENT to 2 for convenience


def test_initial_setup_has_no_more_than_one_incomplete_tournament(usual_setup) -> None:
    assert Tournament.objects.filter(is_complete=False).count() < 2


@pytest.mark.skip(reason="I SAID I'll get to it! Quit nagging me!!")
def test_tournament_is_complete_if_and_only_if_all_boards_have_been_played_at_all_tables(
    usual_setup,
) -> None:
    assert not "I'll get to it, maaan"


@pytest.mark.skip(reason="I SAID I'll get to it! Quit nagging me!!")
def test_tournament_is_complete_if_and_only_if_all_hands_have_been_played_at_all_tables(
    usual_setup,
) -> None:
    assert not "I'll get to it, maaan"


@pytest.fixture
def just_completed(played_almost_to_completion) -> Tournament:
    for p in Player.objects.all():
        print(f"{p.name}: {p.currently_seated=}")

    before = Tournament.objects.filter(is_complete=False).first()
    assert before is not None

    h1 = Hand.objects.get(pk=1)
    west = Player.objects.get_by_name("Adam West")
    h1.add_play_from_player(player=west.libraryThing(), card=Card.deserialize("♠A"))

    return before


def test_completing_one_tournament_causes_a_new_one_to_magically_appear(
    played_almost_to_completion,
) -> None:
    before_qs = Tournament.objects.filter(is_complete=False)
    assert before_qs.count() == 1
    before = before_qs.first()
    assert before is not None

    h1 = Hand.objects.get(pk=1)
    west = Player.objects.get_by_name("Adam West")
    h1.add_play_from_player(player=west.libraryThing(), card=Card.deserialize("♠A"))

    after_qs = Tournament.objects.filter(is_complete=False)
    assert after_qs.count() == 1
    after = after_qs.first()
    assert after is not None

    before.refresh_from_db()
    assert before.is_complete
    assert not after.is_complete

    assert 6 == 9


def test_completing_one_tournament_ejects_players(just_completed) -> None:
    assert not Player.objects.filter(currently_seated=True).exists()
    assert 6 == 9


def test_hand_from_completed_tournament_can_serialize(just_completed, rf) -> None:
    request = rf.get("/wat")
    request.user = Player.objects.get_by_name("Adam West").user
    response = app.views.hand.hand_serialized_view(request, pk=1)
    print(f"{response=}")
