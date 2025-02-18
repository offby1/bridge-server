import collections
import datetime
import logging
import threading

from freezegun import freeze_time
import pytest
from bridge.card import Card
from bridge.contract import Call
from django.contrib import auth
from django.db import connection
from django.db.utils import IntegrityError
from django.http.response import HttpResponseForbidden, HttpResponseRedirect
from django.urls import reverse

import app.views.hand
import app.views.table.details
from app.models import (
    Board,
    Hand,
    NoMoreBoards,
    Player,
    Table,
    TableException,
    Tournament,
    TournamentSignup,
)
import app.models.board
from app.models.tournament import (
    check_for_expirations,
    NotOpenForSignupError,
    PlayerNeedsPartnerError,
    Running,
    OpenForSignup,
)

from .testutils import play_out_hand


logger = logging.getLogger(__name__)


def test_initial_setup_has_no_more_than_one_incomplete_tournament(usual_setup) -> None:
    assert Tournament.objects.filter(is_complete=False).count() < 2


@pytest.fixture
def just_completed(two_boards_one_of_which_is_played_almost_to_completion) -> Tournament:
    for p in Player.objects.all():
        print(f"{p.name}: {p.currently_seated=}")

    before = Tournament.objects.filter(is_complete=False).first()
    assert before is not None

    h1 = Hand.objects.get(pk=1)
    west = Player.objects.get_by_name("Adam West")
    h1.add_play_from_player(player=west.libraryThing(), card=Card.deserialize("♠A"))

    return before


def test_completing_one_tournament_causes_a_new_one_to_magically_appear(
    two_boards_one_of_which_is_played_almost_to_completion,
) -> None:
    Board.objects.filter(pk=2).delete()  # speeds the test up

    tally_before = collections.Counter(Tournament.objects.values_list("is_complete", flat=True))
    assert tally_before == {False: 1}

    before = Tournament.objects.filter(is_complete=False).first()
    assert before is not None

    h1 = Hand.objects.get(pk=1)
    west = Player.objects.get_by_name("Adam West")
    h1.add_play_from_player(player=west.libraryThing(), card=Card.deserialize("♠A"))
    before.refresh_from_db()
    assert before.is_complete

    tally_after = collections.Counter(Tournament.objects.values_list("is_complete", flat=True))
    assert tally_after == {True: 1, False: 1}


def test_completing_one_tournament_ejects_players(
    two_boards_one_of_which_is_played_almost_to_completion,
) -> None:
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


def test_completing_one_tournament_deletes_related_signups(
    two_boards_one_of_which_is_played_almost_to_completion,
    everybodys_password,
) -> None:
    Board.objects.filter(pk=2).delete()  # speeds the test up

    Today = datetime.datetime.fromisoformat("2012-01-10T00:00:00Z")
    Tomorrow = Today + datetime.timedelta(seconds=3600 * 24)
    DayAfter = Tomorrow + datetime.timedelta(seconds=3600 * 24)

    h1 = Hand.objects.get(pk=1)
    the_tournament: Tournament = h1.table.tournament
    the_tournament.signup_deadline = Tomorrow
    the_tournament.play_completion_deadline = DayAfter

    Ricky = Player.objects.create(
        user=auth.models.User.objects.create(username="Ricky Ricardo", password=everybodys_password)
    )
    Lucy = Player.objects.create(
        user=auth.models.User.objects.create(username="Lucy Ricardo", password=everybodys_password)
    )
    Ricky.partner = Lucy
    Lucy.partner = Ricky
    Ricky.save()
    Lucy.save()

    with freeze_time(Today):
        the_tournament.sign_up(Ricky)

        assert TournamentSignup.objects.filter(player=Ricky).exists()

        west = Player.objects.get_by_name("Adam West")
        # hm, I wondder: can we start playing early? Or do I need to scoot the clock forward to Tomorrow?
        h1.add_play_from_player(player=west.libraryThing(), card=Card.deserialize("♠A"))

        assert not TournamentSignup.objects.filter(player=Ricky).exists()


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

        t2 = Table.objects.create_with_two_partnerships(n2, e2, tournament=t1.tournament)
        t2.next_board()

        # Complete the first table.

        h1 = Hand.objects.get(pk=1)
        west = Player.objects.get_by_name("Adam West")
        h1.add_play_from_player(player=west.libraryThing(), card=Card.deserialize("♠A"))

        # Have someone at the first table click "Next Board Plz".
        with pytest.raises(NoMoreBoards):
            t1.next_board()

        client.force_login(t1.seat_set.first().player.user)
        response = client.post(f"/table/{t1.pk}/new-board-plz/")
        assert type(response) is HttpResponseRedirect
        assert response.url == reverse("app:table-list") + "?tournament=1"

        for t in Tournament.objects.all():
            assert t.board_set.count() <= app.models.board.BOARDS_PER_TOURNAMENT

        logger.debug("Ok, this next buncha spew should complete tournament #1")
        play_out_hand(t2)

        t2.tournament.maybe_complete()
        t1.refresh_from_db()
        assert (
            t1.tournament.is_complete
        ), f"Why is {t1.tournament=} ({t1.tournament.status()}) not complete"

        with pytest.raises(NoMoreBoards):
            t1.next_board()

        t2.refresh_from_db()

        with pytest.raises(NoMoreBoards):
            t2.next_board()


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


@pytest.mark.django_db(transaction=True)
def test_that_new_unique_constraint() -> None:
    the_tournament = Tournament.objects.create(display_number=1)
    logger.debug("created %s", the_tournament)

    the_tournament._add_boards_internal(n=2)
    with pytest.raises(IntegrityError):
        the_tournament._add_boards_internal(n=2)

    assert the_tournament.board_set.count() == 2


@pytest.mark.django_db(transaction=True)
def test_concurrency() -> None:
    ThePast = datetime.datetime.fromisoformat("2001-01-01T00:00:00Z")
    TheFuture = datetime.datetime.fromisoformat("2112-01-01T00:00:00Z")
    InBetween = ThePast + datetime.timedelta(seconds=(TheFuture - ThePast).total_seconds() // 2)

    the_tournament = Tournament.objects.create(
        signup_deadline=ThePast, play_completion_deadline=TheFuture
    )

    the_barrier = threading.Barrier(parties=3)

    class BoardAdder(threading.Thread):
        def run(self):
            logger.debug("Hiya")
            try:
                the_tournament.add_boards(n=2, barrier=the_barrier)
            except Exception as e:
                logger.debug("Oy! %s", e)
            finally:
                connection.close()

    with freeze_time(InBetween):
        threads = [BoardAdder() for _ in range(2)]

        for t in threads:
            t.start()
            logger.debug("Started thread %s", t)

        logger.debug("Now ... we wait")
        the_barrier.wait()

        for t in threads:
            t.join()

    assert the_tournament.board_set.count() == 2


def test_signups(nobody_seated) -> None:
    north = Player.objects.get_by_name("Jeremy Northam")
    south = Player.objects.get_by_name("J.D. Souther")
    assert north.partner == south

    running_tournament, _ = Tournament.objects.get_or_create(display_number=1)
    assert not running_tournament.is_complete
    assert running_tournament.status() is Running

    with pytest.raises(NotOpenForSignupError):
        running_tournament.sign_up(north)

    open_tournament, _ = Tournament.objects.get_or_create_tournament_open_for_signups()
    assert not open_tournament.is_complete
    assert open_tournament.status() is OpenForSignup
    open_tournament.sign_up(north)
    actual = set(open_tournament.signed_up_players())
    expected = {north, south}
    assert actual == expected

    east = Player.objects.get_by_name("Clint Eastwood")
    east.break_partnership()
    with pytest.raises(PlayerNeedsPartnerError):
        open_tournament.sign_up(east)

    with freeze_time(open_tournament.signup_deadline + datetime.timedelta(seconds=1)):
        with pytest.raises(NotOpenForSignupError):
            open_tournament.sign_up(east)

    east.partner_with(Player.objects.get_by_name("Adam West"))
    open_tournament.sign_up(east)

    with freeze_time(open_tournament.signup_deadline + datetime.timedelta(seconds=1)):
        check_for_expirations(__name__)
        assert open_tournament.table_set.count() == 1


def test_odd_pair_gets_matched_with_synths(nobody_seated) -> None:
    existing_player_pks = set([p.pk for p in Player.objects.all()])

    north = Player.objects.get_by_name("Jeremy Northam")
    south = Player.objects.get_by_name("J.D. Souther")
    assert north.partner == south

    open_tournament, _ = Tournament.objects.get_or_create_tournament_open_for_signups()
    assert not open_tournament.is_complete
    assert open_tournament.status() is OpenForSignup
    open_tournament.sign_up(north)
    app.models.tournament._do_signup_expired_stuff(open_tournament)

    current_player_pks = set([p.pk for p in Player.objects.all()])
    new_player_pks = current_player_pks - existing_player_pks
    assert len(new_player_pks) == 2

    north.refresh_from_db()
    south.refresh_from_db()

    norths_table = north.current_table
    assert norths_table is not None
    players_at_the_table = set([s.player.pk for s in norths_table.seats])
    assert len(players_at_the_table) == 4
    assert north.pk in players_at_the_table
    assert south.pk in players_at_the_table
    for pk in new_player_pks:
        assert pk in players_at_the_table
        assert Player.objects.get(pk=pk).synthetic
