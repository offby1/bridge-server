import collections
import enum
import itertools
from typing import Any


from django.contrib.auth.models import AnonymousUser, User
from django.core.management import call_command

from app.models import Hand, Player

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


def various_flavors_of_hand():
    hands_by_hand_state_by_tournament_state = collections.defaultdict(dict)
    for hand_state, tournament_state in itertools.product(HandState, TournamentState):
        hands_by_hand_state_by_tournament_state[hand_state][tournament_state] = (
            f"Imagine I'm a {hand_state} hand in a {tournament_state} tournament"
        )

    return dict(hands_by_hand_state_by_tournament_state)


def test_wat():
    assert various_flavors_of_hand() == "cat"
