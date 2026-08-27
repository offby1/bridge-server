import datetime
import logging
import math
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
    TournamentWithdrawal,
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


def _unsettled_hands_in_group(tour: Tournament, group: str) -> list[Hand]:
    """Hands in that round's board group that somebody could still act on."""
    return [
        h
        for h in tour.hands().select_related("board")
        if h.board.group == group and not h.is_complete and not h.is_abandoned
    ]


@pytest.mark.parametrize("boards_per_round_per_table", [1, 2])
def test_splitsville_at_one_table_does_not_stall_the_other_tables(
    db: None, boards_per_round_per_table: int
) -> None:
    """One pair walking out should cost that pair their boards, not freeze the event.

    Call a hand *settled* when nobody can act on it any more -- either it was played
    to the end (`is_complete`) or it was given up on (`is_abandoned`).  A round is over
    once every table has settled all of its boards for that round, where an abandoned
    table counts as done because it deals itself no more boards.

    Two tables.  The pair at the first table splits up, which abandons their hand
    (Player.break_partnership calls abandon_my_hand).  The second table then plays out
    its whole round.  Round 0 is now settled, so round 1 -- board group B -- is due.

    It used not to arrive.  `the_round_just_ended` counted completed hands against the
    number the movement calls for; the abandoned one wasn't among them, so the count
    never got there and Hand.do_end_of_hand_stuff created nothing.  Both tables sat
    idle until the play-completion deadline expired.

    Both board counts matter: with more than one board per round the deserted table
    stops short of its quota, which is exactly what a count against the movement's
    total cannot express.
    """
    tour = create_a_tournament(
        stage="playing",
        num_pairs=4,
        boards_per_round_per_table=boards_per_round_per_table,
    )

    movement = tour.get_movement()
    num_tables = len(movement.table_settings_by_zb_table_number)
    assert num_tables == 2
    assert movement.num_rounds == 2

    round_zero_hands = list(tour.hands())
    assert len(round_zero_hands) == num_tables

    deserted, _still_playing = round_zero_hands

    deserted.North.break_partnership()
    deserted.refresh_from_db()
    assert deserted.is_abandoned
    assert not deserted.is_complete

    # The other table plays its whole round.  Finishing one board deals it the next,
    # so re-ask rather than iterating over a list we captured up front.
    while remaining := _unsettled_hands_in_group(tour, "A"):
        play_out_hand(remaining[0])

    tour.refresh_from_db()

    # Round 0 is settled, so round 1 exists: one fresh hand per table.
    assert tour.hands().filter(board__group="B").count() == num_tables


def test_splitsville_after_the_other_table_has_finished_the_round(db: None) -> None:
    """The same stall, with the two events in the other order.

    Here the second table finishes round 0 first and the split comes afterwards, so the
    hand that settles last is the abandoned one.  Playing a hand is not the only thing
    that can end a round, so Player.abandon_my_hand has to look too -- nothing else is
    going to.
    """
    tour = create_a_tournament(stage="playing", num_pairs=4, boards_per_round_per_table=1)
    num_tables = len(tour.get_movement().table_settings_by_zb_table_number)

    deserted, still_playing = list(tour.hands())

    play_out_hand(still_playing)
    tour.refresh_from_db()
    assert not tour.hands().filter(board__group="B").exists(), (
        "round 1 shouldn't start while the first table is still playing"
    )

    deserted.North.break_partnership()
    tour.refresh_from_db()

    assert tour.hands().filter(board__group="B").count() == num_tables


def test_a_pair_who_quit_are_not_dealt_back_in_next_round(db: None) -> None:
    """Walking out lasts the rest of the tournament, not just the current board.

    The movement is fixed when play starts, so it still schedules the pair who left for
    every later round.  We record their withdrawal and write those hands down abandoned
    instead of seating anybody at them -- both the deserters and whoever they were due
    to meet stay out of it.
    """
    tour = create_a_tournament(stage="playing", num_pairs=4, boards_per_round_per_table=1)

    deserted, still_playing = list(tour.hands())
    quitter = deserted.North
    quitters = {quitter, quitter.partner}

    quitter.break_partnership()

    assert set(
        TournamentWithdrawal.objects.filter(tournament=tour).values_list("player__pk", flat=True)
    ) == {p.pk for p in quitters}

    play_out_hand(still_playing)
    tour.refresh_from_db()

    round_one = list(tour.hands().filter(board__group="B"))
    assert len(round_one) == 2

    dealt_to_a_quitter = [h for h in round_one if quitters & {h.North, h.East, h.South, h.West}]
    assert len(dealt_to_a_quitter) == 1, "the movement should still schedule them exactly once"

    unplayable = dealt_to_a_quitter[0]
    assert unplayable.is_abandoned
    assert quitter.name in unplayable.abandoned_because

    # Nobody is sitting at it -- not the pair who left, nor the pair they'd have met.
    assert not Player.objects.filter(current_hand=unplayable).exists()
    for p in quitters:
        p.refresh_from_db()
        assert p.current_hand is None
        assert not p.currently_seated

    # The other table's round-1 hand is a real one, with four players at it.
    playable = [h for h in round_one if h != unplayable][0]
    assert not playable.is_abandoned
    assert Player.objects.filter(current_hand=playable).count() == 4


def test_a_tournament_finishes_even_if_everybody_quits(db: None) -> None:
    """Both pairs at both tables walking out should end the tournament, not hang it.

    Nothing is left to play, so no hand will ever complete and nobody will abandon one
    either.  Each round we deal is born settled, so `maybe_advance_round` has to keep
    going by itself rather than wait to be called again.
    """
    tour = create_a_tournament(stage="playing", num_pairs=4, boards_per_round_per_table=1)

    for hand in list(tour.hands()):
        hand.North.break_partnership()
        hand.East.break_partnership()

    tour.refresh_from_db()
    assert tour.is_complete
    assert not tour.hands().filter(is_complete=False, abandoned_because__isnull=True).exists()
    assert not Player.objects.currently_seated().exists()


def test_a_pair_who_quit_are_scored_at_average_minus(db: None) -> None:
    """Law 12: the pair at fault get 40%, the pair they stranded get 60%.

    Three tables, so that a board a pair miss still has two results to matchpoint
    against; one board per round, so every table plays the same board each round.  The
    pair at the first table walk out before playing anything, and the rest is played to
    the end.

    Those boards used to be dropped from the scoring outright, which left the deserters
    out of the standings altogether and gave the pair they stranded nothing at all for a
    board they were perfectly willing to play.
    """
    tour = create_a_tournament(stage="playing", num_pairs=6, boards_per_round_per_table=1)
    assert len(tour.get_movement().table_settings_by_zb_table_number) == 3

    deserted = tour.hands().filter(table_display_number=1).get()
    quitters = {deserted.North, deserted.South}
    stranded = {deserted.East, deserted.West}

    deserted.North.break_partnership()

    while not tour.is_complete:
        remaining = [h for h in tour.hands() if not h.is_complete and not h.is_abandoned]
        assert remaining, f"{tour} has nothing left to play but isn't complete"
        play_out_hand(remaining[0])
        tour.refresh_from_db()

    scores = tour.matchpoints_by_pair()

    quitters_score = next(score for pair, score in scores.items() if set(pair) == quitters)
    assert round(quitters_score[1]) == 40, (
        "a pair who played nothing and are at fault throughout score average minus"
    )

    # The pair they walked out on played their other rounds for real, so their total is a
    # blend; what we can say is that they are in the standings, with a score, rather than
    # being silently docked a board.
    stranded_score = next(score for pair, score in scores.items() if set(pair) == stranded)
    assert not math.isnan(stranded_score[1])

    # Everybody who was in the tournament is in the results.
    assert len(scores) == 6
    assert not any(math.isnan(pct) for _, pct in scores.values())


def test_the_boards_a_deserted_table_never_reaches_are_recorded(db: None) -> None:
    """Walking out mid-round costs the whole round, and we write down each board.

    Otherwise the pair left sitting there would be compensated for the boards they were
    denied in later rounds, but get nothing for the rest of the round they were actually
    in the middle of.
    """
    tour = create_a_tournament(stage="playing", num_pairs=6, boards_per_round_per_table=3)

    deserted = tour.hands().filter(table_display_number=1).get()
    deserted.North.break_partnership()

    round_zero_at_that_table = tour.hands().filter(table_display_number=1, board__group="A")
    assert round_zero_at_that_table.count() == 3, (
        "all three of the round's boards are accounted for"
    )
    assert all(h.is_abandoned for h in round_zero_at_that_table)


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
