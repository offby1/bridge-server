import json

import app.views.drf_views
from app.views import player


def test_hand_api_view(usual_setup, rf) -> None:
    v = app.views.drf_views.HandViewSet.as_view({"get": "retrieve"})
    request = rf.get(path="/api/hands/1/")

    north = app.models.player.Player.objects.get_by_name("Jeremy Northam")
    request.user = north.user

    response = v(request, pk=1)

    rendered = response.render()
    data = rendered.data

    match data:
        case {"pk": pk}:
            assert pk == 1


def test_player_by_name_or_pk_view(usual_setup, rf) -> None:
    request = rf.get(path="this field don't matter one bit")

    response = player.by_name_or_pk_view(request, name_or_pk="1")
    assert json.loads(response.content)["name"] == "Jeremy Northam"

    response = player.by_name_or_pk_view(request, name_or_pk="Jeremy Northam")
    assert json.loads(response.content)["name"] == "Jeremy Northam"

    response = player.by_name_or_pk_view(request, name_or_pk="Bogus McHogus")
    assert response.status_code == 404
