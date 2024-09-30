import json

import app.models.player
import app.views.drf_views


def test_card_visibility(usual_setup, rf):
    # fetch the four-hands-view
    # fetch the equivalent data from the API
    # ensure that some cards (i.e., those from players other than the as_viewed_by) aren't visible in the former
    # also ensure those same cards are equally invisible in the latter

    v = app.views.drf_views.BoardViewSet.as_view({"get": "retrieve"})
    request = rf.get(path="/woteva/")

    north = app.models.player.Player.objects.get_by_name("Jeremy Northam")
    request.user = north.user

    actual_board = json.loads(v(request, pk=1).render().content)
    actual_north_cards = actual_board["north_cards"]
    assert actual_north_cards.startswith("♣2")
    assert len(actual_north_cards) == 26

    actual_south_cards = actual_board["south_cards"]
    assert actual_south_cards == ""

    # TODO -- make opening lead (from East), then check south cards again; this time they should be visible.
