import collections

import pytest
from bridge.card import Card

import app.views.hand
from app.models import Board, Hand, Player, Tournament

# mumble import settings, monkeypatch, change BOARDS_PER_TOURNAMENT to 2 for convenience


def test_initial_setup_has_no_more_than_one_incomplete_tournament(usual_setup) -> None:
    assert Tournament.objects.filter(is_complete=False).count() < 2


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
    Board.objects.filter(pk=2).delete()  # speeds the test up

    tally_before = collections.Counter(Tournament.objects.values_list("is_complete", flat=True))
    assert tally_before == {False: 1}

    before = Tournament.objects.filter(is_complete=False).first()
    assert before is not None

    h1 = Hand.objects.get(pk=1)
    west = Player.objects.get_by_name("Adam West")
    h1.add_play_from_player(player=west.libraryThing(), card=Card.deserialize("♠A"))

    tally_after = collections.Counter(Tournament.objects.values_list("is_complete", flat=True))
    assert tally_after == {True: 1, False: 1}


def test_completing_one_tournament_ejects_players(played_almost_to_completion) -> None:
    Board.objects.filter(pk=2).delete()  # speeds the test up

    h1 = Hand.objects.get(pk=1)
    west = Player.objects.get_by_name("Adam West")
    h1.add_play_from_player(player=west.libraryThing(), card=Card.deserialize("♠A"))

    assert not Player.objects.filter(currently_seated=True).exists()


def test_hand_from_completed_tournament_can_serialize(just_completed, rf) -> None:
    request = rf.get("/wat")
    request.user = Player.objects.get_by_name("Adam West").user
    response = app.views.hand.hand_serialized_view(request, pk=1)
    print(f"{response=}")
