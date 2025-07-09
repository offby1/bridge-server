from django.test import Client
from django.urls import reverse

from app.models import Call, Hand, Play, Player


def test_xscript_works_despite_caching_being_hard_yo(usual_setup) -> None:
    h1 = Hand.objects.first()
    assert h1 is not None

    assert len(h1.get_xscript().auction.player_calls) == 0

    c = Call.objects.create(serialized="1♣", hand=h1)
    c.save()

    assert len(h1.get_xscript().auction.player_calls) == 1

    Call.objects.create(serialized="Pass", hand=h1)
    Call.objects.create(serialized="Pass", hand=h1)
    Call.objects.create(serialized="Pass", hand=h1)

    assert len(h1.get_xscript().auction.player_calls) == 4

    assert list(h1.get_xscript().plays()) == []

    Play.objects.create(serialized="♦2", hand=h1)

    plays = list(h1.get_xscript().plays())
    assert len(plays) == 1
    assert plays[0].card.serialize() == "♦2"


def test_play_post_view(usual_setup, rf) -> None:
    c = Client()

    # Anonymous user
    response = c.post(reverse("app:play-post"), data={"card": "C2"})

    assert response.status_code == 302
    assert "/accounts/login/?next=/play/" in response.url

    # Not seated
    player = Player.objects.first()
    c.force_login(player.user)
    response = c.post(reverse("app:play-post"), data={"card": "C2"})
    assert response.status_code == 403
