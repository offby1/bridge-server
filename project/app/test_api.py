import json

from bridge.card import Card, Rank, Suit
from bridge.contract import Bid

import app.models.player
import app.views.drf_views
from app.models import Board, Hand

from .testutils import set_auction_to


def test_card_visibility(usual_setup, rf, settings):
    # fetch the four-hands-view
    # fetch the equivalent data from the API
    # ensure that some cards (i.e., those from players other than the as_viewed_by) aren't visible in the former
    # also ensure those same cards are equally invisible in the latter

    v = app.views.drf_views.BoardViewSet.as_view({"get": "retrieve"})
    request = rf.get(path="/woteva/")

    north = app.models.player.Player.objects.get_by_name("Jeremy Northam")
    request.user = north.user

    expected_model_board = Board.objects.first()

    actual_serialized_board = json.loads(v(request, pk=expected_model_board.pk).render().content)

    actual_north_cards = actual_serialized_board["north_cards"]
    assert actual_north_cards == "♣2♣3♣4♣5♣6♣7♣8♣9♣T♣J♣Q♣K♣A"

    assert "south_cards" not in actual_serialized_board

    # make opening lead (from East)
    east = app.models.player.Player.objects.get_by_name("Clint Eastwood")
    h = Hand.objects.filter(board=expected_model_board).first()
    set_auction_to(Bid(level=1, denomination=Suit.CLUBS), h)
    diamond_two = Card(suit=Suit.DIAMONDS, rank=Rank(2))
    h.add_play_from_player(player=east.libraryThing(hand=h), card=diamond_two)

    # check south cards again; this time they should be visible.
    actual_serialized_board = json.loads(v(request, pk=expected_model_board.pk).render().content)
    actual_south_cards = actual_serialized_board["south_cards"]

    # Yay, now we can see the dummy
    assert len(actual_south_cards) == 26
