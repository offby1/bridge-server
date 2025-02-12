import collections
import datetime

from freezegun import freeze_time
import pytest
from bridge.card import Card
from bridge.contract import Call
from django.contrib import auth
from django.http.response import HttpResponseForbidden

import app.views.hand
import app.views.table.details
from app.models import Board, Hand, NoMoreBoards, Player, Table, TableException, Tournament
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
        with pytest.raises(NoMoreBoards):
            t1.next_board()

        client.force_login(t1.seat_set.first().player.user)
        response = client.post(f"/table/{t1.pk}/new-board-plz/")
        assert response.status_code == 302
        assert response.url == "/table/?tournament=1"

        for t in Tournament.objects.all():
            assert t.board_set.count() <= app.models.board.BOARDS_PER_TOURNAMENT

        play_out_hand(t2)

        t1.refresh_from_db()
        assert t1.tournament.is_complete

        with pytest.raises(NoMoreBoards):
            t1.next_board()

        t2.refresh_from_db()

        with pytest.raises(NoMoreBoards):
            t2.next_board()


def test_signup_deadline(nobody_seated) -> None:
    p1 = Player.objects.first()
    assert p1 is not None
    p3 = Player.objects.exclude(pk=p1.pk).exclude(pk=p1.partner.pk).first()
    assert p3 is not None

    Tuesday = datetime.datetime.fromisoformat("2012-01-10T00:00:00Z")
    Wednesday = Tuesday + datetime.timedelta(seconds=3600 * 24)
    Thursday = Wednesday + datetime.timedelta(seconds=3600 * 24)

    the_tournament = Tournament.objects.first()
    assert the_tournament is not None

    # Ensure out tournament's signup deadline is comfortably in the future.
    the_tournament.signup_deadline = Wednesday
    the_tournament.play_completion_deadline = Thursday
    the_tournament.save()

    with freeze_time(Tuesday):
        # Ensure we can sign up.
        Table.objects.create_with_two_partnerships(p1, p3)

    p2 = p1.partner
    p1.break_partnership()
    p1.partner_with(p2)

    p4 = p3.partner
    p3.break_partnership()
    p3.partner_with(p4)

    # Scoot the clock forward, past the deadline.
    with freeze_time(Thursday):
        # Ensure that we can *not* sign up.
        with pytest.raises(TableException) as e:
            Table.objects.create_with_two_partnerships(p1, p3)

        assert "deadline" in str(e.value)
        assert "has passed" in str(e.value)


def test_play_completion_deadline(usual_setup) -> None:
    # All players are initially seated
    assert not Player.objects.filter(currently_seated=False).exists()

    north = Player.objects.get_by_name("Jeremy Northam")

    Today = datetime.datetime.fromisoformat("2012-01-10T00:00:00Z")
    Tomorrow = Today + datetime.timedelta(seconds=3600 * 24)
    DayAfter = Tomorrow + datetime.timedelta(seconds=3600 * 24)

    table = north.current_table
    the_tournament = table.tournament
    hand = table.current_hand

    with freeze_time(Today):
        the_tournament.signup_deadline = Today
        the_tournament.play_completion_deadline = Tomorrow
        the_tournament.save()

        hand.add_call_from_player(player=north.libraryThing(), call=Call.deserialize("Pass"))

    east = Player.objects.get_by_name("Clint Eastwood")
    with freeze_time(DayAfter):
        with pytest.raises(TableException) as e:
            hand.add_call_from_player(player=east.libraryThing(), call=Call.deserialize("Pass"))

        assert "deadline" in str(e.value)
        assert "has passed" in str(e.value)

        # All players have been ejected
        assert not Player.objects.filter(currently_seated=True).exists()

        hand.refresh_from_db()
        del hand.is_abandoned

        assert hand.is_abandoned
        assert "deadline" in hand.abandoned_because
        assert "has passed" in hand.abandoned_because


def test_deadline_via_view(usual_setup, rf) -> None:
    north = Player.objects.get_by_name("Jeremy Northam")
    Today = datetime.datetime.fromisoformat("2012-01-10T00:00:00Z")
    Tomorrow = Today + datetime.timedelta(seconds=3600 * 24)
    DayAfter = Tomorrow + datetime.timedelta(seconds=3600 * 24)

    table = north.current_table
    the_tournament = table.tournament

    the_tournament.signup_deadline = Today
    the_tournament.play_completion_deadline = Tomorrow
    the_tournament.save()

    table = north.current_table

    with freeze_time(DayAfter):
        request = rf.post("/", data={"call": "Pass"})
        request.user = north.user

        response = app.views.table.details.call_post_view(request, table.current_hand.pk)
        assert response.status_code == HttpResponseForbidden.status_code
        assert b"deadline" in response.content
        assert b"has passed" in response.content


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
