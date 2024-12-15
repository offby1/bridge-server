from django.contrib import auth

import app.views.board
from app.models import Board, Player, Tournament


def test_board_list_view(db, rf, everybodys_password) -> None:
    while Tournament.objects.count() < 2:
        Tournament.objects.create()

    some_user, _ = auth.models.User.objects.get_or_create(
        username="bob", password=everybodys_password
    )
    some_player, _ = Player.objects.get_or_create(user=some_user)
    assert some_player is not None

    request = rf.get("/woteva/", data={"per_page": Board.objects.count()})

    request.user = some_player.user

    response = app.views.board.board_list_view(request=request)

    assert response.status_code == 200
    response.render()
    expected_anchors = {
        f"""<a href="/board/{pk}/">""" for pk in Board.objects.values_list("pk", flat=True).all()
    }
    content = response.content.decode()

    for a in sorted(expected_anchors):
        assert a in content
