import json

import app.models.player
import app.views.drf_views
from app.models import Board


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

    # TODO -- make opening lead (from East), then check south cards again; this time they should be visible.
