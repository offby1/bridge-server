import pytest
from django.contrib import auth
from django.db import IntegrityError
from django.test import Client
from django.urls import reverse

from .models import Player, Seat, Table


def test_we_gots_a_home_page():
    c = Client()
    response = c.get("/")
    assert b"Welcome" in response.content


@pytest.fixture()
def bob(db):
    u = auth.models.User.objects.create_user(username="Bob", password="Bob")
    return Player.objects.create(user=u, looking_for_partner=True)


@pytest.fixture()
def usual_setup(db):
    t = Table.objects.create()
    for username, attr in (
        ("Bob", "north"),
        ("Carol", "east"),
        ("Ted", "south"),
        ("Alice", "west"),
    ):
        u = auth.models.User.objects.create_user(username=username, password=username)
        p = Player.objects.create(user=u)
        Seat.objects.create(direction=attr[0].upper(), player=p, table=t)


def test_player_names_are_links_to_detail_page(usual_setup):
    p = Player.objects.get_by_name("Bob")

    link = p.as_link()
    assert ">Bob<" in link
    assert "href='/player/" in link


def test_only_bob_can_see_bobs_cards(usual_setup):
    c = Client()
    assert c.login(username="Bob", password="Bob"), "I guess I don't know how to make a test log in"
    response = c.get(reverse("app:player", kwargs=dict(pk=1)))

    assert response.context["show_cards_for"] == ["Bob"]


def test_player_cannot_be_at_two_seats(bob):
    t = Table.objects.create()

    Seat.objects.create(direction="N", player=Player.objects.get_by_name("Bob"), table=t)

    with pytest.raises(IntegrityError):
        Seat.objects.create(direction="E", player=Player.objects.get_by_name("Bob"), table=t)


def test_player_cannot_be_in_two_tables(usual_setup):
    bob = Player.objects.get_by_name("Bob")

    t2 = Table.objects.create()

    with pytest.raises(IntegrityError):
        Seat.objects.create(direction="E", player=bob, table=t2)

    # TODO -- make this pass too
    # bobs_table = Player.objects.get_by_name("Bob").table
    # bobs_table.somehow_mark_this_hand_as_over()
    # c()


def test_player_ceases_looking_for_partner_once_seated(bob):
    t = Table.objects.create()
    Seat.objects.create(direction="E", player=bob, table=t)
    bob.refresh_from_db()
    assert not bob.looking_for_partner


def test_view_filter(usual_setup):
    c = Client()
    response = c.get("/players/?lookin_for_love=true")
    assert "All 0 players." in response.content.decode()


def test_cant_just_make_up_directions(bob):
    t = Table.objects.create()
    with pytest.raises(IntegrityError):
        Seat.objects.create(direction="!", player=bob, table=t)
