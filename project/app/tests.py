import pytest
from django.contrib import auth
from django.core.exceptions import ValidationError
from django.db import DatabaseError
from django.test import Client
from django.urls import reverse

from .models import Player, Seat, Table


def test_we_gots_a_home_page():
    c = Client()
    response = c.get("/")
    assert b"Welcome" in response.content


@pytest.fixture()
def usual_setup(db):
    t = Table.objects.create(name="The Table")

    Seat.create_for_table(t)
    for username, direction in (("Bob", "N"), ("Carol", "E"), ("Ted", "S"), ("Alice", "W")):
        s = Seat.objects.get(table=t, direction=direction)
        u = auth.models.User.objects.create_user(username=username, password=username)
        Player.objects.create(user=u, seat=s)


def test_player_names_are_links_to_detail_page(usual_setup):
    p = Player.objects.get(user__username="Bob")

    link = p.as_link()
    assert ">Bob," in link
    assert "href='/player/" in link


def test_no_bogus_directions(usual_setup):
    t = Table.objects.first()
    with pytest.raises(ValidationError):
        Seat.objects.create(table=t, direction="X")


def test_no_more_than_four_players_per_table(usual_setup):
    u = auth.models.User.objects.create(username="Spock")
    with pytest.raises(DatabaseError):
        Player.objects.create(user=u, seat=Seat.objects.first())


def test_only_bob_can_see_bobs_cards(usual_setup):
    c = Client()
    assert c.login(username="Bob", password="Bob"), "I guess I don't know how to make a test log in"
    response = c.get(reverse("app:player", kwargs=dict(pk=1)))

    assert response.context["show_cards_for"] == ["Bob"]
