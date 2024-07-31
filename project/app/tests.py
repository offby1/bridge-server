import pytest
from django.contrib import auth
from django.db import DatabaseError
from django.test import Client

from .models import Player, Seat, Table


def test_we_gots_a_home_page():
    c = Client()
    response = c.get("/")
    assert b"Welcome" in response.content


def test_player_names_are_links_to_detail_page(db):
    u = auth.models.User.objects.create(username="Bob")
    t = Table.objects.create(name="The Table")
    s = Seat.objects.create(table=t, direction="N")
    p = Player.objects.create(user=u, seat=s)

    link = p.as_link()
    assert ">Bob," in link
    assert "href='/player/" in link


def test_no_bogus_directions(db):
    t = Table.objects.create(name="The Table")
    with pytest.raises(Exception):
        Seat.objects.create(table=t, direction="X")


def test_no_more_than_four_players_per_table(db):
    t = Table.objects.create(name="The Table")

    Seat.create_for_table(t)
    for username, direction in (("Bob", "N"), ("Carol", "E"), ("Ted", "S"), ("Alice", "W")):
        s = Seat.objects.get(table=t, direction=direction)
        u = auth.models.User.objects.create(username=username)
        Player.objects.create(user=u, seat=s)

    u = auth.models.User.objects.create(username="Spock")
    with pytest.raises(DatabaseError):
        Player.objects.create(user=u, seat=s)
