import base64
import json
from html.parser import HTMLParser
from typing import cast

import pytest
from django.core.cache import cache
from django.test import RequestFactory
from django.test.client import Client
from django.urls import reverse

from app.models import Hand, Player, Tournament, TournamentSignup
from app.views import player, tournament
from app.views.misc import AuthedHttpRequest


def test_player_by_name_or_pk_view(usual_setup: Hand, rf: RequestFactory) -> None:
    request = rf.get(path="this field don't matter one bit")

    response = player.by_name_or_pk_view(request, name_or_pk="1")
    assert json.loads(response.content)["name"] == "Jeremy Northam"

    response = player.by_name_or_pk_view(request, name_or_pk="Jeremy Northam")
    assert json.loads(response.content)["name"] == "Jeremy Northam"

    response = player.by_name_or_pk_view(request, name_or_pk="Bogus McHogus")
    assert response.status_code == 404


def test_compatibility_with_login(usual_setup: Hand, rf: RequestFactory) -> None:
    jeremys_player_id = "1"
    request = rf.get(path="/")
    # Note: this is the *player* ID, not the django *user* ID.
    response = player.by_name_or_pk_view(request, name_or_pk="1")
    assert response.status_code == 200
    assert json.loads(response.content)["name"] == "Jeremy Northam"

    c = Client()

    response = c.get(
        reverse("app:login"),
        headers={"Authorization": "Basic " + base64.b64encode(b"Jeremy Northam:.").decode()},  # type: ignore [arg-type]
    )

    assert response.status_code == 200
    assert "sessionid" in response.cookies

    response = c.get(
        reverse("app:player-by-name-or-pk", kwargs={"name_or_pk": jeremys_player_id}),
    )
    assert json.loads(response.content)["name"] == "Jeremy Northam"


def test_tournament_view_after_splitsville(usual_setup: Hand, rf: RequestFactory):
    some_player = Player.objects.first()
    assert some_player is not None
    some_player.break_partnership()
    cache.clear()

    t = Tournament.objects.first()
    assert t is not None

    request = rf.get("/woteva")
    request.user = some_player.user
    tournament.tournament_view(cast(AuthedHttpRequest, request), t.pk)


def test_player_list_renders_for_someone_looking_for_a_partner(usual_setup: Hand) -> None:
    """The partner-hunting list is the page you land on right after Splitsville.

    Its button comes from a different context than the player detail page's, and
    FASTDEV_STRICT_IF turns a `{% if %}` on a missing key into an error rather than a
    silent False -- so a key added to one context and not the other 500s the page.
    """
    lonely = Player.objects.get_by_name("Jeremy Northam")
    lonely.break_partnership()

    c = Client()
    c.force_login(lonely.user)
    response = c.get(reverse("app:players"), {"has_partner": "False", "exclude_me": "True"})

    assert response.status_code == 200
    assert 'value="partnerup"' in response.content.decode()


def test_splitsville_warns_a_player_who_is_mid_tournament(usual_setup: Hand) -> None:
    """The button says "Splitsville!!"; the warning says what that costs.

    A pair who walk out mid-tournament forfeit every board they had left, at 40% each,
    so the page has to say so before they click rather than let them find out from the
    standings afterwards.
    """
    seated = Player.objects.get_by_name("Jeremy Northam")
    assert seated.currently_seated
    tour = seated.current_hand.tournament
    assert not tour.is_complete

    c = Client()
    c.force_login(seated.user)
    content = c.get(reverse("app:player", args=[seated.pk])).content.decode()

    assert "data-confirm=" in content
    assert f"quits tournament #{tour.display_number}" in content
    assert "40%" in content


def test_splitsville_mentions_a_signup_they_would_lose(nobody_seated: None) -> None:
    """Not yet playing, but signed up: breaking up drops the pair from the tournament."""
    signed_up = Player.objects.get_by_name("Jeremy Northam")
    assert not signed_up.currently_seated
    tour = TournamentSignup.objects.get(player=signed_up).tournament

    c = Client()
    c.force_login(signed_up.user)
    content = c.get(reverse("app:player", args=[signed_up.pk])).content.decode()

    assert f"signed up for tournament #{tour.display_number}" in content
    assert "40%" not in content, "nothing is forfeited yet; don't talk about scores"


def test_splitsville_does_not_nag_when_it_costs_nothing(
    nobody_seated_nobody_signed_up: None,
) -> None:
    """No tournament to forfeit, no signup to lose: just let them click the button."""
    unseated = Player.objects.get_by_name("Jeremy Northam")
    assert not unseated.currently_seated
    assert unseated.partner is not None
    assert not TournamentSignup.objects.filter(player=unseated).exists()

    c = Client()
    c.force_login(unseated.user)
    content = c.get(reverse("app:player", args=[unseated.pk])).content.decode()

    assert "Splitsville" in content, "the button should still be there"
    assert "data-confirm=" not in content


def test_bot_checkbox_toggle(usual_setup: Hand, rf: RequestFactory) -> None:
    some_player: Player | None = Player.objects.first()
    assert some_player is not None
    assert not some_player.synthetic

    some_player.allow_bot_to_play_for_me = False
    some_player.save()

    request = rf.post("/woteva")
    request.user = some_player.user

    class CheckboxParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.checkbox_checked = False
            self.found_checkbox = False

        def handle_starttag(self, tag, attrs):
            if tag == "input":
                attrs_dict = dict(attrs)
                if attrs_dict.get("id") == "bot-plays-for-me-switch":
                    self.found_checkbox = True
                    self.checkbox_checked = "checked" in attrs_dict

    def box_is_checked():
        __traceback_hide__ = True  # noqa: F841
        html = response.render().content.decode()
        parser = CheckboxParser()
        parser.feed(html)
        assert parser.found_checkbox, "Checkbox element not found in HTML"
        return parser.checkbox_checked

    def allowed():
        __traceback_hide__ = True  # noqa: F841
        some_player.refresh_from_db(fields=["allow_bot_to_play_for_me"])
        return some_player.allow_bot_to_play_for_me

    response = player.bot_checkbox_view(request, some_player.pk)
    response.render()
    print(response.content.decode())
    assert box_is_checked()
    assert allowed()

    # Once again

    response = player.bot_checkbox_view(request, some_player.pk)
    response.render()
    print(response.content.decode())
    assert not box_is_checked()
    assert not allowed()


@pytest.mark.parametrize(
    "url",
    [
        ("/",),
        ("/some-random-404",),
        ("/admin"),
    ],
)
def test_adds_x_robots_tag_header(url: str, db: None):
    c = Client()
    response = c.get(url)
    assert response.headers["X-Robots-Tag"] == "none"


def test_serves_robots_dot_txt(db: None):
    c = Client()
    response = c.get("/robots.txt")
    assert response.status_code == 200
    assert b"Disallow:" in response.content
