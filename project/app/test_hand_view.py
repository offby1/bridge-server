import app.views.drf_views


def test_hand_api_view(usual_setup, rf):
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
