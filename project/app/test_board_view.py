import re

from django.contrib import auth

import app.views.board
from app.models import Board, Player, Tournament


def test_board_list_view(db, rf, everybodys_password) -> None:
    Tournament.objects.create()

    some_user, _ = auth.models.User.objects.get_or_create(
        username="bob", password=everybodys_password
    )
    some_player, _ = Player.objects.get_or_create(user=some_user)
    assert some_player is not None

    request = rf.get("/woteva/", data={"per_page": max(1, Board.objects.count())})
    request.user = some_player.user

    response = app.views.board.BoardListView.as_view()(request=request)

    assert response.status_code == 200
    response.render()
    expected_anchors = {
        f"""<a href="/board/{pk}/">""" for pk in Board.objects.values_list("pk", flat=True).all()
    }
    content = response.content.decode()

    for a in sorted(expected_anchors):
        assert a in content

    for t in Tournament.objects.all():
        boards = Board.objects.filter(tournament=t).values_list("pk", flat=True).all()

        request = rf.get("/woteva/", data={"tournament": t.pk})
        request.user = some_player.user

        response = app.views.board.BoardListView.as_view()(request=request)
        assert response.status_code == 200

        response.render()
        content = response.content.decode()

        actual_anchors = set(re.findall("""<a href="/board/[0-9]+/">""", content))
        expected_anchors = {f"""<a href="/board/{pk}/">""" for pk in boards}
        assert actual_anchors == expected_anchors
