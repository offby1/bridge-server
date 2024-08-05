import pytest
from django.contrib import auth
from django.test import Client
from django.urls import reverse

from .models import Player, Table, TableException


def test_we_gots_a_home_page():
    c = Client()
    response = c.get("/")
    assert b"Welcome" in response.content


@pytest.fixture()
def usual_setup(db):
    creation_kwargs = {}
    for username, attr in (
        ("Bob", "north"),
        ("Carol", "east"),
        ("Ted", "south"),
        ("Alice", "west"),
    ):
        u = auth.models.User.objects.create_user(username=username, password=username)
        p = Player.objects.create(user=u)
        creation_kwargs[attr] = p

    Table.objects.create(**creation_kwargs)


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


def test_player_cannot_be_at_two_seats(db):
    for username in (
        "Bob",
        "Ted",
        "Alice",
    ):
        u = auth.models.User.objects.create_user(username=username, password=username)
        Player.objects.create(user=u)

    with pytest.raises(TableException) as e:
        Table.objects.create(
            north=Player.objects.get_by_name("Bob"),
            east=Player.objects.get_by_name("Bob"),
            south=Player.objects.get_by_name("Ted"),
            west=Player.objects.get_by_name("Alice"),
        )
    assert str(e.value) == "Yo cuz you can't sit in more than one seat at a table"


def test_player_cannot_be_in_two_tables(usual_setup):
    n = "Steve Northup"
    s = "J. D. Souther"
    w = "Adam West"
    for username in (
        n,
        s,
        w,
    ):
        u = auth.models.User.objects.create_user(username=username, password=username)
        Player.objects.create(user=u)

    def c():
        Table.objects.create(
            north=Player.objects.get_by_name(n),
            east=Player.objects.get_by_name("Bob"),
            south=Player.objects.get_by_name(s),
            west=Player.objects.get_by_name(w),
        )

    with pytest.raises(TableException) as e:
        c()

    assert str(e.value) == "Bob is already seated"

    # TODO -- make this pass too
    # bobs_table = Player.objects.get_by_name("Bob").table
    # bobs_table.somehow_mark_this_hand_as_over()
    # c()


def test_player_ceases_looking_for_partner_once_seated(db):
    creation_kwargs = {}
    for username, attr in (
        ("Bob", "north"),
        ("Carol", "east"),
        ("Ted", "south"),
        ("Alice", "west"),
    ):
        u = auth.models.User.objects.create_user(username=username, password=username)
        p = Player.objects.create(user=u, looking_for_partner=True)
        creation_kwargs[attr] = p

    Table.objects.create(**creation_kwargs)
    for p in Player.objects.all():
        assert not p.looking_for_partner


def test_view_filter(usual_setup):
    c = Client()
    response = c.get("/players/?lookin_for_love=true")
    assert "All 0 players." in response.content.decode()
