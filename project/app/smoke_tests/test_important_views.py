import collections
import datetime
import enum
import itertools
import logging
from typing import Any

from freezegun import freeze_time
import pytest

from django.contrib.auth.models import AnonymousUser, User
from django.core.management import call_command

from app.models import Hand, Player, Tournament
from app.models.tournament import _do_signup_expired_stuff

from app.views.hand import hand_archive_view, hand_detail_view

from app.testutils import play_out_hand

logger = logging.getLogger()


class HandState(enum.Enum):
    incomplete = enum.auto()
    abandoned = enum.auto()
    complete = enum.auto()


class TournamentState(enum.Enum):
    incomplete = enum.auto()
    complete = enum.auto()


@pytest.fixture
def _completed_tournament(db: Any):
    Signup = datetime.datetime.fromisoformat("2000-01-01T00:00:00Z")
    PlayCompletion = Signup + datetime.timedelta(seconds=24 * 3600)
    t = Tournament.objects.create(
        boards_per_round_per_table=2,
        signup_deadline=Signup,
        play_completion_deadline=PlayCompletion,
    )

    with freeze_time(Signup - datetime.timedelta(seconds=1)):
        p1 = Player.objects.create_synthetic()
        p2 = Player.objects.create_synthetic()
        p2.partner = p1
        p2.save()
        p1.partner = p2
        p1.save()
        t.sign_up_player_and_partner(p1)

    with freeze_time(Signup + datetime.timedelta(seconds=1)):
        _do_signup_expired_stuff(t)
        h1: Hand | None = t.hands().first()
        assert h1 is not None
        play_out_hand(h1)

    with freeze_time(PlayCompletion + datetime.timedelta(seconds=1)):
        t.abandon_all_hands(reason="Play completion deadline has passed")
        h = t.hands().filter(abandoned_because__isnull=False).first()
        assert h is not None
        yield t


@pytest.fixture
def smoke_case_1(db: Any):
    call_command("loaddata", "smoke-case-1")


@pytest.fixture
def various_flavors_of_hand(db: Any, smoke_case_1, _completed_tournament: Tournament):
    assert datetime.datetime.utcnow().year == 2000

    hands_by_hand_state_by_tournament_state: dict[HandState, dict[TournamentState, Hand]] = (
        collections.defaultdict(dict)
    )
    for hand_state, tournament_state in itertools.product(HandState, TournamentState):
        the_tournament = None
        match tournament_state:
            case TournamentState.incomplete:
                the_tournament = Tournament.objects.get(pk=1)
            case TournamentState.complete:
                the_tournament = _completed_tournament  # can't use the existing "just_completed" fixture cuz its primary keys collide with smoke-case-1 :-(
            case _:
                assert not f"Well, this is embarrassing.  wtf is {tournament_state=}?"

        the_hand = None
        match hand_state:
            case HandState.complete:
                the_hand = the_tournament.hands().filter(abandoned_because__isnull=True).first()
            case HandState.abandoned:
                the_hand = the_tournament.hands().filter(abandoned_because__isnull=False).first()
            case HandState.incomplete:
                # Can't have a complete tournament with an incomplete hand.
                if tournament_state == TournamentState.complete:
                    continue

                the_hand = Hand.objects.get(pk=10)
            case _:
                assert not f"Well, this is embarrassing.  wtf is {hand_state=}?"

        assert the_hand is not None, (
            f"well, so far {dict(hands_by_hand_state_by_tournament_state)=}"
        )

        the_hand.board.tournament = the_tournament
        the_hand.board.save()

        hands_by_hand_state_by_tournament_state[hand_state][tournament_state] = the_hand

    return dict(hands_by_hand_state_by_tournament_state)


def test_both_important_views(rf: Any, various_flavors_of_hand) -> None:
    for hand_state, hands_by_tournament_state in various_flavors_of_hand.items():
        for tournament_state, hand in hands_by_tournament_state.items():
            request = rf.get("/woteva/", data={"pk": hand.pk})

            # Various flavors of user
            anonymoose = AnonymousUser()
            has_no_player = User.objects.get(username="admin")
            played_the_hand = hand.players().first().user
            did_not_play_the_hand = Player.objects.create_synthetic().user

            for user in (None, anonymoose, has_no_player, played_the_hand, did_not_play_the_hand):
                request.user = user
                assert hand_archive_view(request=request, pk=hand.pk).status_code < 500
                assert hand_detail_view(request=request, pk=hand.pk).status_code < 500
