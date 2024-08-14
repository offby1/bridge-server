import re

import bridge.seat
import pytest
from asgiref.sync import async_to_sync
from django.contrib import auth
from django.db import IntegrityError
from django.test import Client
from django.urls import reverse

from .models import Player, PlayerException, Seat, Table
from .views import player_list_view


def test_we_gots_a_home_page():
    c = Client()
    response = c.get("/")
    assert b"Welcome" in response.content


@pytest.fixture()
def bob(db):
    u = auth.models.User.objects.create_user(username="Bob", password="Bob")
    return Player.objects.create(user=u)


@pytest.fixture()
def usual_setup(db):
    t = Table.objects.create()
    for username, attr in (
        ("Bob", bridge.seat.Seat.NORTH),
        ("Carol", bridge.seat.Seat.EAST),
        ("Ted", bridge.seat.Seat.SOUTH),
        ("Alice", bridge.seat.Seat.WEST),
    ):
        u = auth.models.User.objects.create_user(username=username, password=username)
        p = Player.objects.create(user=u)
        Seat.objects.create(direction=attr.value, player=p, table=t)


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

    Seat.objects.create(
        direction=bridge.seat.Seat.NORTH.value,
        player=Player.objects.get_by_name("Bob"),
        table=t,
    )

    with pytest.raises(IntegrityError):
        Seat.objects.create(
            direction=bridge.seat.Seat.EAST.value,
            player=Player.objects.get_by_name("Bob"),
            table=t,
        )


def test_player_cannot_be_in_two_tables(usual_setup):
    bob = Player.objects.get_by_name("Bob")

    t2 = Table.objects.create()

    with pytest.raises(IntegrityError):
        Seat.objects.create(direction=bridge.seat.Seat.EAST.value, player=bob, table=t2)

    # TODO -- make this pass too
    # bobs_table = Player.objects.get_by_name("Bob").table
    # bobs_table.somehow_mark_this_hand_as_over()
    # c()


def test_view_filter(usual_setup, rf):
    request = rf.post("/players/", data=dict(lookin_for_love=True))
    response = player_list_view(request)
    text = response.content.decode()

    assert re.search(r"0 / 4\s+players\.", text)


def test_cant_just_make_up_directions(bob):
    t = Table.objects.create()
    with pytest.raises(Exception) as e:
        Seat.objects.create(direction=1234, player=bob, table=t)

    assert "not a valid Seat" in str(e.value)


def test_breaking_up_is_hard_to_do(usual_setup):
    Bob = Player.objects.get_by_name("Bob")
    Carol = Player.objects.get_by_name("Carol")
    Ted = Player.objects.get_by_name("Ted")
    assert Bob.partner == Ted
    assert Ted.partner == Bob

    # No exception because Bob is already partnered with Ted, so an exception would serve no purpose.
    Bob.partner_with(Ted)

    with pytest.raises(PlayerException):
        Bob.partner_with(Carol)

    Bob.break_partnership()
    Bob.refresh_from_db()
    Ted.refresh_from_db()
    assert Bob.partner is None
    assert Ted.partner is None


def test_multiple_windows_out_of_sync(db):
    Player.objects.create(
        user=auth.models.User.objects.create_user(username="bob", password="bob"),
    )
    Player.objects.create(
        user=auth.models.User.objects.create_user(username="kat", password="kat"),
    )

    client_1 = Client()
    client_1.login(username="bob", password="bob")

    client_2 = Client()
    client_2.login(username="bob", password="bob")

    response = client_1.post(
        "/player/2/",
        data=dict(me=1, them=2, action="partnerup"),
        follow=True,
    )

    form = response.context["form"]
    assert form.data["action"] == "splitsville"

    response = client_2.post(
        "/player/2/",
        data=dict(me=1, them=2, action="partnerup"),
        follow=True,
    )
    form = response.context["form"]
    assert form.data["action"] == "splitsville"


async def collect_async_response_stuff(async_response):
    response = []
    async for wat in async_response:
        response.append(wat)
        break  # don't loop through "all" of them since there's an infinite number!
    return response


# https://discord.com/channels/856567261900832808/1273356653605027951/1273356653605027951
def test_SES(db):
    client = Client()
    response = client.get("/events/")

    bytestring = async_to_sync(collect_async_response_stuff)(response)[0]
    wtf = [b.strip() for b in bytestring.split(b":")]
    wtf = [b for b in wtf if b]
    assert wtf == [b"event", b"stream-open\ndata"]
