import pytest
from django.contrib import auth
from django.test import Client

from .models import Player, Table


def test_we_gots_a_home_page():
    c = Client()
    response = c.get("/")
    assert b"Welcome" in response.content


def test_player_names_are_links_to_detail_page(db):
    u = auth.models.User.objects.create(username="Bob")
    t = Table.objects.create(name="The Table")
    p = Player.objects.create(user=u, table=t)

    link = p.as_link()
    assert ">Bob," in link
    assert "href='/player/" in link


def test_no_more_than_four_players_per_table(db):
    t = Table.objects.create(name="The Table")

    for username in ("Bob", "Carol", "Ted", "Alice"):
        u = auth.models.User.objects.create(username=username)
        Player.objects.create(user=u, table=t)

    u = auth.models.User.objects.create(username="Spock")
    with pytest.raises(Exception) as e:
        Player.objects.create(user=u, table=t)
    assert "more than four" in str(e.value)
