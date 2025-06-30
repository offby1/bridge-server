from django.contrib.auth.models import AnonymousUser
from django.core.management import call_command

import pytest

import bridge.card
import bridge.contract

from .models import Board, Hand, Player, Tournament
from .views.board import board_archive_view
from .views.hand import _interactive_view, HandListView, hand_serialized_view
from .views.tournament import tournament_view


def test__interactive_view_doesnt_do_a_shitton_of_queries(
    usual_setup: Hand, rf, django_assert_max_num_queries
) -> None:
    h = usual_setup

    def next_caller(current_caller):
        table = h.auction.table
        return table.get_lho(current_caller)

    caller = h.auction.allowed_caller()

    def c(call: bridge.contract.Call) -> None:
        nonlocal caller
        Hand.objects.get(pk=h.pk).add_call_from_player(player=caller, call=call)
        caller = next_caller(caller)

    c(bridge.contract.Pass)
    c(bridge.contract.Pass)
    c(bridge.contract.Pass)
    c(bridge.contract.Bid(level=1, denomination=bridge.card.Suit.CLUBS))
    c(bridge.contract.Pass)
    c(bridge.contract.Pass)
    c(bridge.contract.Double)
    c(bridge.contract.Pass)
    c(bridge.contract.Pass)

    request = rf.get("/woteva/", data={"pk": h.pk})
    p = Player.objects.first()
    assert p is not None
    request.user = p.user

    with django_assert_max_num_queries(35):
        _interactive_view(request, h)


def test_tournament_detail_view_doesnt_do_a_shitton_of_queries(
    nearly_completed_tournament, rf, django_assert_max_num_queries
) -> None:
    request = rf.get("/woteva/")
    p = Player.objects.first()
    assert p is not None
    request.user = p.user

    with django_assert_max_num_queries(10):
        tournament_view(request, "1")


def test_again_but_bigger(db: None, rf, django_assert_max_num_queries) -> None:
    call_command("loaddata", "completed-tournament-20-players")

    request = rf.get("/woteva/")
    request.user = None

    with django_assert_max_num_queries(171):
        tournament_view(request, "1")


def test_hand_list_view(nearly_completed_tournament, rf, django_assert_max_num_queries) -> None:
    request = rf.get("/woteva/")
    request.user = AnonymousUser()

    with django_assert_max_num_queries(2):
        wat = HandListView.as_view()(request)
        wat.render()


@pytest.mark.parametrize(
    ["username", "expected_num_queries"],
    [
        ["Clint Eastwood", 5],
        [None, 2],
    ],
)
def test_board_archive_view(
    nearly_completed_tournament, rf, django_assert_max_num_queries, username, expected_num_queries
) -> None:
    request = rf.get("/woteva/")

    if username is None:
        request.user = AnonymousUser()
    else:
        request.user = Player.objects.get_by_name(username).user

    board = Board.objects.first()
    assert board is not None
    with django_assert_max_num_queries(expected_num_queries):
        board_archive_view(request, pk=board.pk)


def test_hand_serialzed_view(
    nearly_completed_tournament, rf, django_assert_max_num_queries
) -> None:
    request = rf.get("/woteva/", headers={"accept": "application/json"})
    player = Player.objects.first()
    assert player is not None
    request.user = player.user

    hand = Hand.objects.first()
    assert hand is not None

    # This does a fair number of queries, but they oughtn't be counted against hand_serialized_view.
    for t in Tournament.objects.all():
        t.get_movement()

    # Damn, 19 queries? wtf are they?
    with django_assert_max_num_queries(19):
        response = hand_serialized_view(request, pk=hand.pk)

    assert response.headers["Content-Type"].startswith("application/json")
    assert response.status_code == 200
