from django.contrib import auth
from django.test import Client
from .models import Club, Player, Table


def test_we_gots_a_home_page():
    c = Client()
    response = c.get("/")
    assert b"Welcome" in response.content


def test_player_names_are_links_to_detail_page(db):
    u = auth.models.User.objects.create(username="Bob")
    t = Table.objects.create(name="The Table", club=Club.objects.create(name="The Club"))
    p = Player.objects.create(user=u, table=t)

    link = p.as_link()
    assert ">Bob<" in link
    assert "href='/player/" in link
