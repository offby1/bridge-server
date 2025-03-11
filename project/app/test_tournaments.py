import collections
import datetime
import logging

from freezegun import freeze_time
import pytest
from bridge.card import Card
from bridge.contract import Call
from django.contrib import auth
from django.http.response import HttpResponseForbidden

import app.views.hand
import app.views.table.details
from app.models import (
    Board,
    Hand,
    Player,
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


def test_signups(nobody_seated) -> None:
    north = Player.objects.get_by_name("Jeremy Northam")
    south = Player.objects.get_by_name("J.D. Souther")
    assert north.partner == south

    running_tournament, _ = Tournament.objects.get_or_create(display_number=1)
    assert not running_tournament.table_set.exists()

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
    west = Player.objects.get_by_name("Adam West")
    east.break_partnership()
    with pytest.raises(PlayerNeedsPartnerError):
        open_tournament.sign_up(east)

    with freeze_time(open_tournament.signup_deadline + datetime.timedelta(seconds=1)):
        with pytest.raises(NotOpenForSignupError):
            open_tournament.sign_up(east)

    east.partner_with(west)
    open_tournament.sign_up(east)

    actual = set(open_tournament.signed_up_players())
    expected = {north, south, east, west}
    assert actual == expected

    with freeze_time(open_tournament.signup_deadline + datetime.timedelta(seconds=1)):
        check_for_expirations(__name__)
        assert open_tournament.table_set.count() == 1

    with freeze_time(open_tournament.signup_deadline - datetime.timedelta(seconds=10)):
        east.break_partnership()

        assert not TournamentSignup.objects.filter(
            tournament=open_tournament, player=east
        ).exists(), f"Hey, {east.name} went splitsville, but is still signed up"


def test_odd_pair_gets_matched_with_synths(nobody_seated) -> None:
    existing_player_pks = set([p.pk for p in Player.objects.all()])

    north = Player.objects.get_by_name("Jeremy Northam")
    south = Player.objects.get_by_name("J.D. Souther")
    assert north.partner == south

    open_tournament, _ = Tournament.objects.get_or_create_tournament_open_for_signups()
    assert not open_tournament.is_complete
    assert open_tournament.status() is OpenForSignup
    open_tournament.sign_up(north)
    assert not open_tournament.table_set.exists()

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


def test_which_hand(usual_setup: None, everybodys_password) -> None:
    t = Tournament.objects.first()
    assert t is not None

    for name in ["n2", "e2", "s2", "w2"]:
        Player.objects.create(
            user=auth.models.User.objects.create(username=name, password=everybodys_password),
        )

    assert not t.which_hands(four_players={1, 3, 5, 7}).exists()
    assert t.which_hands(four_players={1, 2, 3, 4}).exists()


def test_end_of_round_stuff_happens(usual_setup) -> None:
    tour = Tournament.objects.first()
    tour.check_consistency()
    table = tour.table_set.first()
    for _ in range(3):
        play_out_hand(table)
        table.next_board()
