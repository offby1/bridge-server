import collections

import pytest
from bridge.card import Card
from django.contrib import auth

import app.views.hand
import app.views.table.details
from app.models import Board, Hand, Player, Table, TableException, Tournament
import app.models.board

from .testutils import play_out_hand

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


def test_tournament_end(
    nearly_completed_tournament, everybodys_password, monkeypatch, client
) -> None:
    assert Board.objects.count() == 1
    with monkeypatch.context() as m:
        t1 = Table.objects.first()
        assert t1 is not None
        assert Table.objects.count() == 1

        m.setattr(app.models.board, "BOARDS_PER_TOURNAMENT", 1)
        assert app.models.board.BOARDS_PER_TOURNAMENT == 1

        # Create a second table in this tournament.
        for name in ("n2", "e2", "s2", "w2"):
            u = auth.models.User.objects.create(username=name, password=everybodys_password)
            Player.objects.create(user=u)
        n2 = Player.objects.get_by_name("n2")
        n2.partner_with(Player.objects.get_by_name("s2"))

        e2 = Player.objects.get_by_name("e2")
        e2.partner_with(Player.objects.get_by_name("w2"))

        t2 = Table.objects.create_with_two_partnerships(n2, e2)
        # Complete the first table.

        h1 = Hand.objects.get(pk=1)
        west = Player.objects.get_by_name("Adam West")
        h1.add_play_from_player(player=west.libraryThing(), card=Card.deserialize("♠A"))

        # Have someone at the first table click "Next Board Plz".
        assert t1.next_board() is None

        client.force_login(t1.seat_set.first().player.user)
        response = client.post(f"/table/{t1.pk}/new-board-plz/")
        assert response.status_code == 302
        assert response.url == "/table/?tournament=1"

        for t in Tournament.objects.all():
            assert t.board_set.count() <= app.models.board.BOARDS_PER_TOURNAMENT

        play_out_hand(t2)

        t1.refresh_from_db()
        assert t1.tournament.is_complete
        assert t1.next_board() is None

        t2.refresh_from_db()
        assert t2.next_board() is None


def test_no_stragglers(
    nearly_completed_tournament, everybodys_password, monkeypatch, client
) -> None:
    assert Board.objects.count() == 1
    with monkeypatch.context() as m:
        t1 = Table.objects.first()
        assert t1 is not None
        assert Table.objects.count() == 1
        print(f"{t1.current_hand.board=}")
        m.setattr(app.models.board, "BOARDS_PER_TOURNAMENT", 1)
        assert app.models.board.BOARDS_PER_TOURNAMENT == 1

        # Complete the first table.

        h1 = Hand.objects.get(pk=1)
        west = Player.objects.get_by_name("Adam West")
        h1.add_play_from_player(player=west.libraryThing(), card=Card.deserialize("♠A"))
        assert t1.tournament.is_complete

        north = Player.objects.get_by_name("Jeremy Northam")
        west = Player.objects.get_by_name("Adam West")

        t2 = Table.objects.create_with_two_partnerships(north, west)
        print(f"{t2.hand_set.all()=}")
        assert t2 is None or t2.hand_set.count() > 0
        print(f"{t2.current_hand.board=}")
