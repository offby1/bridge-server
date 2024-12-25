import json
import logging

from bridge.card import Card, Rank, Suit
from bridge.contract import Bid
from rest_framework.test import (  # type: ignore [import-untyped]
    APIRequestFactory,
    force_authenticate,
)

import app.models.player
import app.views.drf_views
from app.models import Board, Call, Hand, Play, Player, Table, logged_queries
from app.serializers import ReadOnlyCallSerializer, ReadOnlyPlaySerializer

from .testutils import set_auction_to


def test_card_visibility(usual_setup, rf) -> None:
    # fetch the four-hands-view
    # fetch the equivalent data from the API
    # ensure that some cards (i.e., those from players other than the as_viewed_by) aren't visible in the former
    # also ensure those same cards are equally invisible in the latter

    v = app.views.drf_views.BoardViewSet.as_view({"get": "retrieve"})
    request = rf.get(path="/woteva/")

    north = app.models.player.Player.objects.get_by_name("Jeremy Northam")
    request.user = north.user

    expected_model_board = Board.objects.first()
    assert expected_model_board is not None

    actual_serialized_board = json.loads(v(request, pk=expected_model_board.pk).render().content)

    actual_north_cards = actual_serialized_board["north_cards"]
    assert actual_north_cards == "♣2♣3♣4♣5♣6♣7♣8♣9♣T♣J♣Q♣K♣A"

    assert "south_cards" not in actual_serialized_board

    # make opening lead (from East)
    east = app.models.player.Player.objects.get_by_name("Clint Eastwood")
    h: Hand | None = Hand.objects.filter(board=expected_model_board).first()
    assert h is not None
    set_auction_to(Bid(level=1, denomination=Suit.CLUBS), h)
    diamond_two = Card(suit=Suit.DIAMONDS, rank=Rank(2))
    h.add_play_from_player(player=east.libraryThing(), card=diamond_two)

    # check south cards again; this time they should be visible.
    actual_serialized_board = json.loads(v(request, pk=expected_model_board.pk).render().content)
    actual_south_cards = actual_serialized_board["south_cards"]

    # Yay, now we can see the dummy
    assert len(actual_south_cards) == 26


def test_call_post(usual_setup) -> None:
    t = Table.objects.first()
    assert t is not None
    h = t.current_hand
    assert h is not None

    north = h.player_who_may_call
    assert north.name == "Jeremy Northam"

    three_notrump = Bid(denomination=None, level=3)
    factory = APIRequestFactory()
    request = factory.post(
        "/api/calls/", {"serialized": three_notrump.serialize(), "hand_id": h.pk}, format="json"
    )
    h.bust_cache()
    force_authenticate(request, user=north.user)
    view = app.views.drf_views.CallViewSet.as_view(actions={"post": "create"})

    response = view(request)

    assert response.status_code == 201
    xs = h.get_xscript()
    a = xs.auction

    assert len(a.player_calls) == 1
    first_player_call = a.player_calls[0]

    assert first_player_call.player.name == "Jeremy Northam"

    assert first_player_call.call.level == 3
    assert first_player_call.call.denomination is None


def test_play_post(usual_setup) -> None:
    t = Table.objects.first()
    assert t is not None
    h = t.current_hand
    assert h is not None

    set_auction_to(Bid(level=1, denomination=Suit.CLUBS), h)
    east = h.player_who_may_play
    assert east.name == "Clint Eastwood"

    diamond_two = Card(suit=Suit.DIAMONDS, rank=Rank(2))
    factory = APIRequestFactory()
    request = factory.post(
        "/api/plays/", {"serialized": diamond_two.serialize(), "hand_id": h.pk}, format="json"
    )
    force_authenticate(request, user=east.user)
    view = app.views.drf_views.PlayViewSet.as_view(actions={"post": "create"})

    response = view(request)
    assert response.status_code == 201
    h = Hand.objects.get(pk=h.pk)
    xs = h.get_xscript()
    assert len(xs.tricks) == 1
    first_trick = xs.tricks[0]
    assert len(first_trick) == 1
    first_play = first_trick[0]

    assert first_play.seat.name == "East"
    assert first_play.card == diamond_two


def test_player_query(usual_setup, rf):
    player_one = Player.objects.first()
    assert player_one is not None

    v = app.views.drf_views.PlayerViewSet.as_view({"get": "list"})

    request = rf.get(path="/woteva/")
    request.user = player_one.user
    response = v(request).render()

    # assert that the response contains four users, including player_one
    assert response.data["count"] == 4
    assert player_one.name in {result["name"] for result in response.data["results"]}

    request = rf.get(path=f"/woteva/?name={player_one.name}")
    request.user = player_one.user
    response = v(request).render()
    assert response.data["count"] == 1
    assert player_one.name in {result["name"] for result in response.data["results"]}


def test_player_permissions(usual_setup):
    player_one = Player.objects.first()
    assert player_one is not None
    assert player_one.allow_bot_to_play_for_me is True

    v = app.views.drf_views.PlayerViewSet.as_view({"put": "update"})
    factory = APIRequestFactory()
    request = factory.put(
        path="it always surprises me that this path doesn't matter",
        data={"allow_bot_to_play_for_me": False},
        format="json",
    )
    force_authenticate(request, user=player_one.user)

    response = v(request, pk=player_one.pk).render()
    assert 200 <= response.status_code < 400
    assert response.data["allow_bot_to_play_for_me"] is False

    player_two = Player.objects.exclude(pk=player_one.pk).first()
    assert player_two is not None
    request = factory.put(
        path="it always surprises me that this path doesn't matter",
        data={"allow_bot_to_play_for_me": True},
        format="json",
    )
    force_authenticate(request, user=player_two.user)
    response = v(request, pk=player_one.pk).render()

    assert response.status_code > 400
    assert (
        json.loads(response.content)
        == f"You, requester_pk={player_two.user.pk}, may not futz with player target_pk={player_one.user.pk}"
    )
    player_one.refresh_from_db()
    assert player_one.allow_bot_to_play_for_me is False


def test_serialized_call(played_to_completion) -> None:
    c1 = Call.objects.first()
    data = ReadOnlyCallSerializer(c1).data
    assert data == {"serialized": "1♣", "hand": {"id": 1, "table": 1, "board": 1}, "seat_pk": 1}


def test_xscript_works_despite_caching_being_hard_yo(usual_setup):
    h1 = Hand.objects.first()
    assert h1 is not None

    assert len(h1.get_xscript().auction.player_calls) == 0

    c = Call.objects.create(serialized="1♣", hand=h1)
    c.save()

    assert len(h1.get_xscript().auction.player_calls) == 1

    Call.objects.create(serialized="Pass", hand=h1)
    Call.objects.create(serialized="Pass", hand=h1)
    Call.objects.create(serialized="Pass", hand=h1)

    assert len(h1.get_xscript().auction.player_calls) == 4

    assert list(h1.get_xscript().plays()) == []

    Play.objects.create(serialized="♦2", hand=h1)

    plays = list(h1.get_xscript().plays())
    assert len(plays) == 1
    assert plays[0].card.serialize() == "♦2"


def skip_test_serialized_play(played_almost_to_completion) -> None:
    p1 = Play.objects.first()
    assert p1 is not None

    data = ReadOnlyPlaySerializer(p1).data
    assert data == {"serialized": "♦2", "hand": {"id": 1, "table": 1, "board": 1}, "seat_pk": 2}

    with logged_queries():
        p52 = Play.objects.create(hand=p1.hand, serialized="♠A")
    logger = logging.getLogger("app")
    logger.debug(f"test just created {p52.serialized}")
    data = ReadOnlyPlaySerializer(p52).data
    assert data == {"serialized": "♠A", "hand": {"id": 1, "table": 1, "board": 1}, "seat_pk": 4}
