import collections
import enum
import itertools
from typing import Any

import pytest

from django.contrib.auth.models import AnonymousUser, User
from django.core.management import call_command

from app.models import Hand, Player, Tournament

from app.views.hand import hand_archive_view, hand_detail_view


def test_both_important_views(db: Any, rf: Any) -> None:
    call_command("loaddata", "smoke-case-1")

    # What is interesting about this hand?
    # - it's incomplete (has just a single call, and no plays)
    # - following from the above, it's not abandoned
    # - its tournament is still running
    hand_pk = 10

    request = rf.get("/woteva/", data={"pk": hand_pk})

    hand = Hand.objects.get(pk=hand_pk)

    # Various flavors of user
    anonymoose = AnonymousUser()
    has_no_player = User.objects.get(username="admin")
    played_the_hand = hand.players().first().user
    did_not_play_the_hand = Player.objects.create_synthetic().user

    for user in (None, anonymoose, has_no_player, played_the_hand, did_not_play_the_hand):
        request.user = user
        hand_archive_view(request=request, pk=hand_pk)
        hand_detail_view(request=request, pk=hand_pk)


class HandState(enum.Enum):
    incomplete = enum.auto()
    abandoned = enum.auto()
    complete = enum.auto()


class TournamentState(enum.Enum):
    incomplete = enum.auto()
    complete = enum.auto()


@pytest.fixture
def _completed_tournament(db: Any):
    t = Tournament.objects.create(boards_per_round_per_table=1)
    return t


@pytest.fixture
def various_flavors_of_hand(db: Any, _completed_tournament: Tournament):
    call_command("loaddata", "smoke-case-1")

    hands_by_hand_state_by_tournament_state = collections.defaultdict(dict)
    for hand_state, tournament_state in itertools.product(HandState, TournamentState):
        the_tournament = None
        match tournament_state:
            case TournamentState.incomplete:
                the_tournament = Tournament.objects.get(pk=1)
            case _:
                the_tournament = _completed_tournament  # can't use the existing "just_completed" fixture cuz its primary keys collide with smoke-case-1 :-(

        the_hand = None
        match hand_state:
            case HandState.abandoned | HandState.complete:
                assert not "I am still dumb"
            case HandState.incomplete:
                the_hand = Hand.objects.get(pk=10)
            case _:
                assert not f"Well, this is embarrassing.  wtf is {hand_state=}?"

        assert the_hand is not None

        the_hand.board.tournament = the_tournament
        the_hand.board.save()

        hands_by_hand_state_by_tournament_state[hand_state][tournament_state] = the_hand

    return dict(hands_by_hand_state_by_tournament_state)


def test_wat(various_flavors_of_hand):
    assert various_flavors_of_hand == "cat"
