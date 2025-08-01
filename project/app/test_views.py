import base64
import json

from django.conf import settings
from django.core.cache import cache
from django.test.client import Client
from django.urls import reverse

from app.models import Player, Tournament
from app.views import player, tournament


def test_player_by_name_or_pk_view(usual_setup, rf) -> None:
    request = rf.get(path="this field don't matter one bit")

    response = player.by_name_or_pk_view(request, name_or_pk="1")
    assert json.loads(response.content)["name"] == "Jeremy Northam"

    response = player.by_name_or_pk_view(request, name_or_pk="Jeremy Northam")
    assert json.loads(response.content)["name"] == "Jeremy Northam"

    response = player.by_name_or_pk_view(request, name_or_pk="Bogus McHogus")
    assert response.status_code == 404


def test_compatibility_with_three_way_login(usual_setup, rf) -> None:
    jeremys_player_id = "1"
    request = rf.get(path="/")
    # Note: this is the *player* ID, not the django *user* ID.
    response = player.by_name_or_pk_view(request, name_or_pk="1")
    assert response.status_code == 200
    assert json.loads(response.content)["name"] == "Jeremy Northam"

    c = Client()

    response = c.get(
        reverse("app:three-way-login"),
        headers={
            "Authorization": "Basic "
            + base64.b64encode(f"{jeremys_player_id}:{settings.API_SKELETON_KEY}".encode()).decode()
        },  # type: ignore [arg-type]
    )

    assert response.status_code == 200
    assert "sessionid" in response.cookies

    response = c.get(
        reverse("app:player-by-name-or-pk", kwargs={"name_or_pk": jeremys_player_id}),
    )
    assert json.loads(response.content)["name"] == "Jeremy Northam"


def test_tournament_view_after_splitsville(usual_setup, rf):
    some_player = Player.objects.first()
    some_player.break_partnership()
    cache.clear()

    request = rf.get("/woteva")
    request.user = some_player
    tournament.tournament_view(request, Tournament.objects.first().pk)


def test_bot_checkbox_toggle(usual_setup, rf) -> None:
    some_player: Player | None = Player.objects.first()
    assert some_player is not None
    assert not some_player.synthetic

    some_player.allow_bot_to_play_for_me = False
    some_player.save()

    request = rf.post("/woteva")
    request.user = some_player.user

    def box_is_checked():
        __traceback_hide__ = True  # noqa: F841
        return "checked />" in response.render().text

    def allowed():
        __traceback_hide__ = True  # noqa: F841
        some_player.refresh_from_db(fields=["allow_bot_to_play_for_me"])
        return some_player.allow_bot_to_play_for_me

    response = player.bot_checkbox_view(request, some_player.pk)
    assert box_is_checked()
    assert allowed()

    # Once again

    response = player.bot_checkbox_view(request, some_player.pk)
    assert not box_is_checked()
    assert not allowed()
