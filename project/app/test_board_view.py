from typing import Any

import app.views.board
from app.models import Board, Player


def test_board_list_view(usual_setup: None, rf: Any) -> None:
    some_player = Player.objects.first()
    assert some_player is not None

    request = rf.get("/woteva/")

    request.user = some_player.user

    response = app.views.board.board_list_view(request=request)

    assert response.status_code == 200
    response.render()
    expected_anchors = {
        f"""<a href="/board/{pk}/">"""
        for pk in Board.objects.values_list("pk", flat=True).order_by("pk").all()
    }
    content = response.content.decode()
    for a in expected_anchors:
        assert a in content
