import datetime
import logging
from typing import cast

import pytest
import time_machine
from django.contrib import auth
from django.http.response import HttpResponseForbidden
from django.test import RequestFactory
from django.utils.timezone import now

import app.models.board
import app.views.hand
import app.views.misc
import app.views.table.details
from app.models import (
    Board,
    Hand,
    HandError,
    Player,
    Tournament,
    TournamentSignup,
)
from app.models.tournament import (
    NotOpenForSignupError,
    OpenForSignup,
    PlayerNeedsPartnerError,
    Running,
    advance_expired_tournaments,
)
from bridge.contract import Call

from .testutils import create_a_tournament, play_out_hand, play_out_round

logger = logging.getLogger(__name__)


def test_initial_setup_has_no_more_than_one_incomplete_tournament(usual_setup: Hand) -> None:
    assert Tournament.objects.incompletes().count() < 2


def _tally_ho() -> dict[bool, int]:
    incomplete_count = Tournament.objects.incompletes().count()
    complete_count = Tournament.objects.count() - incomplete_count
    rv = {}
    if complete_count:
        rv[True] = complete_count
    if incomplete_count:
        rv[False] = incomplete_count
    return rv


def test_completing_one_tournament_does_not_cause_a_new_one_to_magically_appear_or_anything(
    two_boards_one_of_which_is_played_almost_to_completion: None,
) -> None:
    tally_before = _tally_ho()
    assert tally_before == {False: 1}

    before = Tournament.objects.incompletes().first()
    assert before is not None

    hand = before.hands().first()
    assert hand is not None

    play_out_round(before)

    before.refresh_from_db()
    assert before.is_complete

    tally_after = _tally_ho()
    assert tally_after == {True: 1}


def test_completing_one_tournament_ejects_players(
    two_boards_one_of_which_is_played_almost_to_completion: None,
) -> None:
    tournament = Tournament.objects.incompletes().first()
    assert tournament is not None
    hand = tournament.hands().first()
    assert hand is not None

    while not tournament.is_complete:
        play_out_round(tournament)

    assert not Player.objects.currently_seated().exists()


def test_hand_from_completed_tournament_can_serialize(
    just_completed: Tournament, rf: RequestFactory
) -> None:
    request = rf.get("/wat")
    request.user = Player.objects.get_by_name("Adam West").user
    response = app.views.hand.hand_serialized_view(
        cast(app.views.misc.AuthedHttpRequest, request), pk=1
    )
    print(f"{response=}")


def test_completing_one_tournament_deletes_related_signups(
    two_boards_one_of_which_is_played_almost_to_completion: None,
    everybodys_password: str,
) -> None:
    Board.objects.filter(pk=2).delete()  # speeds the test up

    Today = datetime.datetime.fromisoformat("2012-01-10T00:00:00Z")
    Tomorrow = Today + datetime.timedelta(seconds=3600 * 24)
    DayAfter = Tomorrow + datetime.timedelta(seconds=3600 * 24)

    h1 = Hand.objects.get(pk=1)
    the_tournament: Tournament = h1.tournament
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

    with time_machine.travel(Today, tick=False):
        the_tournament.sign_up_player_and_partner(Ricky)

        assert TournamentSignup.objects.filter(player=Ricky).exists()

        while not the_tournament.is_complete:
            # hm, I wondder: can we start playing early? Or do I need to scoot the clock forward to Tomorrow?
            play_out_round(the_tournament)

        assert not TournamentSignup.objects.filter(player=Ricky).exists()


def test_play_completion_deadline(usual_setup: Hand) -> None:
    # All players are initially seated

    assert Player.objects.currently_seated().count() == Player.objects.count()

    north = Player.objects.get_by_name("Jeremy Northam")

    SignupDeadlineDay = datetime.datetime.fromisoformat("2012-01-10T00:00:00Z")
    PlayCompletionDeadline = SignupDeadlineDay + datetime.timedelta(seconds=3600 * 24)
    DayAfter = PlayCompletionDeadline + datetime.timedelta(seconds=3600 * 24)

    hand = north.current_hand
    assert hand is not None
    the_tournament = hand.tournament

    with time_machine.travel(SignupDeadlineDay, tick=False):
        the_tournament.signup_deadline = SignupDeadlineDay
        the_tournament.play_completion_deadline = PlayCompletionDeadline
        the_tournament.save()

        hand.add_call(call=Call.deserialize("Pass"))

    with time_machine.travel(DayAfter, tick=False):
        advance_expired_tournaments()
        with pytest.raises(HandError):
            hand.add_call(call=Call.deserialize("Pass"))

        # All players have been ejected
        assert Player.objects.currently_seated().count() == 0

        hand = Hand.objects.get(pk=hand.pk)

        assert hand.is_abandoned
        assert "deadline" in hand.abandoned_because
        assert "has passed" in hand.abandoned_because


def test_a_completed_hand_survives_the_play_completion_deadline(db: None) -> None:
    """A hand that was played to the end keeps its score when the deadline passes.

    Finishing a hand does not set `Player.current_hand` back to None; it goes on pointing
    at the finished hand until that player is dealt into another one.  So a pair who have
    played all the boards at their table, while another table is still going, are left
    pointing at a completed hand.  When the deadline then arrives, abandoning that hand
    would contradict the score we show for it.
    """
    the_tournament = create_a_tournament(stage="playing", boards_per_round_per_table=2)

    # Table 1 plays both of its boards; table 2 never finishes even one, so the round
    # doesn't end and nobody moves on.
    while (
        h := the_tournament.hands().filter(table_display_number=1, is_complete=False).first()
    ) is not None:
        play_out_hand(h)

    completed_hand = the_tournament.hands().filter(table_display_number=1).last()
    assert completed_hand is not None
    assert completed_hand.is_complete
    parked = list(Player.objects.filter(current_hand=completed_hand))
    assert len(parked) == 4, "Table 1's pairs should still be sitting at their finished hand"

    deadline = now() + datetime.timedelta(hours=1)
    the_tournament.play_completion_deadline = deadline
    the_tournament.save()

    with time_machine.travel(deadline + datetime.timedelta(hours=1), tick=False):
        advance_expired_tournaments()

    completed_hand.refresh_from_db()
    assert completed_hand.is_complete
    assert not completed_hand.is_abandoned
    assert completed_hand.abandoned_because is None

    # The players did still get up from the table.
    assert not Player.objects.filter(current_hand=completed_hand).exists()

    # The hand that really was still in progress is the one that gets abandoned.
    unfinished = the_tournament.hands().filter(table_display_number=2).first()
    assert unfinished is not None
    assert unfinished.is_abandoned
    assert "has passed" in unfinished.abandoned_because


def test_deadline_via_view(usual_setup: Hand, rf: RequestFactory) -> None:
    north = Player.objects.get_by_name("Jeremy Northam")
    Today = datetime.datetime.fromisoformat("2012-01-10T00:00:00Z")
    Tomorrow = Today + datetime.timedelta(seconds=3600 * 24)
    DayAfter = Tomorrow + datetime.timedelta(seconds=3600 * 24)

    current_hand = north.current_hand
    the_tournament = current_hand.tournament

    the_tournament.signup_deadline = Today
    the_tournament.play_completion_deadline = Tomorrow
    the_tournament.save()

    with time_machine.travel(DayAfter, tick=False):
        request = rf.post("/", data={"call": "Pass"})
        request.user = north.user

        response = app.views.table.details.call_post_view(request)
        assert response.status_code == HttpResponseForbidden.status_code
        assert b"deadline" in response.content
        assert b"has passed" in response.content


def test_signups(nobody_seated_nobody_signed_up: None) -> None:
    north = Player.objects.get_by_name("Jeremy Northam")
    south = Player.objects.get_by_name("J.D. Souther")
    assert north.partner == south

    running_tournament, _ = Tournament.objects.get_or_create(display_number=1)

    assert not running_tournament.is_complete
    assert running_tournament.status() is Running

    with pytest.raises(NotOpenForSignupError):
        running_tournament.sign_up_player_and_partner(north)

    open_tournament, _ = Tournament.objects.get_or_create_tournament_open_for_signups()
    assert not open_tournament.is_complete
    assert open_tournament.status() is OpenForSignup

    open_tournament.sign_up_player_and_partner(north)
    actual = set(open_tournament.signed_up_players())
    expected = {north, south}
    assert actual == expected

    east = Player.objects.get_by_name("Clint Eastwood")
    west = Player.objects.get_by_name("Adam West")
    east.break_partnership()
    with pytest.raises(PlayerNeedsPartnerError):
        open_tournament.sign_up_player_and_partner(east)

    with time_machine.travel(
        open_tournament.signup_deadline + datetime.timedelta(seconds=1), tick=False
    ):
        with pytest.raises(NotOpenForSignupError):
            open_tournament.sign_up_player_and_partner(east)

    east.partner_with(west)
    open_tournament.sign_up_player_and_partner(east)

    actual = set(open_tournament.signed_up_players())
    expected = {north, south, east, west}
    assert actual == expected

    with time_machine.travel(
        open_tournament.signup_deadline - datetime.timedelta(seconds=10), tick=False
    ):
        east.break_partnership()

        assert not TournamentSignup.objects.filter(
            tournament=open_tournament, player=east
        ).exists(), f"Hey, {east.name} went splitsville, but is still signed up"


def test_odd_pair_gets_matched_with_synths(nobody_seated: None) -> None:
    existing_player_pks = set([p.pk for p in Player.objects.all()])
    assert existing_player_pks == {1, 2, 3, 4}

    north = Player.objects.get_by_name("Jeremy Northam")
    south = Player.objects.get_by_name("J.D. Souther")
    assert north.partner == south

    open_tournament, _ = Tournament.objects.get_or_create_tournament_open_for_signups()
    assert not open_tournament.is_complete
    assert open_tournament.status() is OpenForSignup

    assert not open_tournament.hands().exists()

    s1 = Player.objects.create_synthetic()
    s2 = Player.objects.create_synthetic()
    s1.partner_with(s2)

    open_tournament.sign_up_player_and_partner(s1)
    open_tournament.signup_deadline = now() - datetime.timedelta(seconds=10)

    app.models.tournament._do_signup_expired_stuff(open_tournament)

    assert TournamentSignup.objects.count() == 8

    current_player_pks = set([p.pk for p in Player.objects.all()])
    new_player_pks = current_player_pks - existing_player_pks
    assert len(new_player_pks) == 4


def test_end_of_round_stuff_happens(usual_setup: Hand) -> None:
    tour = Tournament.objects.first()
    assert tour is not None

    tour.check_consistency()

    def some_incomplete_hand() -> Hand:
        for h in tour.hands():
            if not h.is_complete:
                return h

        raise Exception("I should have never gotten here.  I am mollifying mypy.")

    hand = some_incomplete_hand()
    play_out_hand(hand)
    assert tour.rounds_played() == (0, 1)

    hand = some_incomplete_hand()
    play_out_hand(hand)
    assert tour.rounds_played() == (0, 2)

    hand = some_incomplete_hand()
    play_out_hand(hand)
    assert tour.rounds_played() == (1, 0)


@pytest.mark.xfail(
    reason="Tournament.rounds_played counts only complete hands, so an abandoned one never lets the count reach the round boundary, and no later round is ever created.  See TODO.txt, the Splitsville item.",
    strict=True,
)
def test_splitsville_at_one_table_does_not_stall_the_other_tables(db: None) -> None:
    """One pair walking out should cost that pair their boards, not freeze the event.

    Call a hand *settled* when nobody can act on it any more -- either it was played
    to the end (`is_complete`) or it was given up on (`is_abandoned`).  A round is over
    once every hand in it is settled.  Django has no such field today; the tournament
    asks only about `is_complete`, which is the whole bug.

    Two tables, one board per round.  The pair at the first table splits up, which
    abandons their hand (Player.break_partnership calls abandon_my_hand).  The second
    table then plays its round-0 board to completion.  Both round-0 hands are now
    settled, so round 1 is due.

    Today it never arrives: Tournament.rounds_played counts only `is_complete` hands,
    the abandoned one isn't among them, so `the_round_just_ended` returns None and
    Hand.do_end_of_hand_stuff creates nothing.  Both tables sit idle until the
    play-completion deadline expires.
    """
    tour = create_a_tournament(stage="playing", num_pairs=4, boards_per_round_per_table=1)

    movement = tour.get_movement()
    num_tables = len(movement.table_settings_by_zb_table_number)
    assert num_tables == 2
    assert movement.num_rounds == 2

    round_zero_hands = list(tour.hands())
    assert len(round_zero_hands) == num_tables

    deserted, still_playing = round_zero_hands

    deserted.North.break_partnership()
    deserted.refresh_from_db()
    assert deserted.is_abandoned
    assert not deserted.is_complete

    play_out_hand(still_playing)
    tour.refresh_from_db()

    # Both round-0 hands are settled, so round 1 should exist: one fresh hand per
    # table, on top of the two hands from round 0.
    assert tour.hands().count() == 2 * num_tables


def test_get_movement_with_odd_pairs_before_synths_are_created(nobody_seated: None) -> None:
    """A tournament whose signup deadline passes with an odd number of pairs --
    but *before* the synth-padding has run -- used to 500 the tournament page:
    get_movement() built a phantom pair and tripped `assert num_phantoms == 0`.

    This reproduces that first-page-view-after-the-deadline state by backdating
    the deadline without calling _do_signup_expired_stuff, which is what creates
    the padding synths once the clock gets to this tournament."""
    open_tournament, _ = Tournament.objects.get_or_create_tournament_open_for_signups()

    s1 = Player.objects.create_synthetic()
    s2 = Player.objects.create_synthetic()
    s1.partner_with(s2)
    open_tournament.sign_up_player_and_partner(s1)

    open_tournament.signup_deadline = now() - datetime.timedelta(seconds=10)
    open_tournament.save()

    assert not open_tournament.hands().exists()
    pairs_before = len(list(open_tournament.signed_up_pairs()))
    assert pairs_before % 2 == 1  # odd -- would have needed a phantom

    movement = open_tournament.get_movement()  # used to raise AssertionError

    # The odd pairs got padded with a real synthetic partnership, not a phantom,
    # so the cached movement is fully playable.
    assert movement.num_phantoms == 0
    assert len(list(open_tournament.signed_up_pairs())) == pairs_before + 1


def test_no_boards_vanishes_after_play_deadline(fresh_tournament: Tournament) -> None:
    assert fresh_tournament.hands().count() == 0
    assert fresh_tournament.pk is not None
    assert fresh_tournament.play_completion_deadline is not None
    with time_machine.travel(
        fresh_tournament.play_completion_deadline + datetime.timedelta(seconds=20), tick=False
    ):
        fresh_tournament.maybe_complete()
        assert fresh_tournament.pk is None
