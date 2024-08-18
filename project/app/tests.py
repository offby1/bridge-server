import importlib
import json
import re

import bridge.seat
import pytest
from django.contrib import auth
from django.contrib.auth.models import AnonymousUser
from django.db import IntegrityError
from django.test import Client
from django.urls import reverse

from .models import Message, Player, PlayerException, Seat, Table
from .views import lobby, player


def test_we_gots_a_home_page():
    c = Client()
    response = c.get("/")
    assert b"Welcome" in response.content


@pytest.fixture
def bob(db):
    u = auth.models.User.objects.create_user(username="Bob", password="Bob")
    return Player.objects.create(user=u)


@pytest.fixture
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

    def r():
        return c.get(reverse("app:player", kwargs=dict(pk=1)), follow=True)

    response = r()
    assert not response.context.get("show_cards_for")

    c.login(username="Bob", password="Bob")

    response = r()
    assert response.context["show_cards_for"] == [Player.objects.get_by_name("Bob")]


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


def test_view_filter(usual_setup, rf):
    request = rf.post("/players/", data=dict(lookin_for_love=True))
    response = player.player_list_view(request)
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
    Alice = Player.objects.get_by_name("Alice")

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

    # No exception because Carol is single
    Alice.break_partnership()
    Carol.refresh_from_db()
    Bob.partner_with(Carol)


def test_multiple_windows_in_sync(db):
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


def test_player_channnel_encoding():
    assert Message.channel_name_from_player_pks(1, 2) == "players:1_2"
    assert Message.channel_name_from_player_pks(20, 10) == "players:10_20"

    assert Message.player_pks_from_channel_name("tewtally bogus") is None
    assert Message.player_pks_from_channel_name("players:10_20") == {10, 20}
    assert Message.player_pks_from_channel_name("players:20_10") == {10, 20}


def test_sending_lobby_messages(usual_setup, rf):
    def say_hey(user=None):
        if user is None:
            user = AnonymousUser()

        request = rf.post(
            "/send_lobby_message/",
            content_type="application/json",
            data=json.dumps(dict(message="hey you")),
        )
        request.user = user
        return request

    response = lobby.send_lobby_message(say_hey())
    assert response.status_code == 403  # client isn't authenticated
    assert response.content == b"Go away, anonymous scoundrel"

    response = lobby.send_lobby_message(say_hey(user=Player.objects.get_by_name("Bob").user))
    assert response.status_code == 200


def test_sending_player_messages(usual_setup, rf):
    bob = Player.objects.get_by_name("Bob")

    def hey_bob(*, target=None, sender_player=None):
        if target is None:
            target = bob

        if sender_player is None:
            user = AnonymousUser()
        else:
            user = sender_player.user

        request = rf.post(
            reverse("app:send_player_message", args=[target.pk]),
            content_type="application/json",
            data=json.dumps({"message": "hey you"}),
        )

        request.user = user
        return player.send_player_message(request, recipient_pk=target.pk)

    response = hey_bob()
    assert response.status_code == 403  # client isn't authenticated
    assert response.content == b"Go away, anonymous scoundrel"

    response = hey_bob(sender_player=Player.objects.get_by_name("Ted"))
    assert response.status_code == 403  # we're both at a table, so we can't talk
    assert b"already seated" in response.content

    for n in ("lobbyboy", "lobbygirl"):
        Player.objects.create(
            user=auth.models.User.objects.create_user(
                username=n,
                password=n,
            ),
        )

    lobbyboy = Player.objects.get_by_name("lobbyboy")
    lobbygirl = Player.objects.get_by_name("lobbygirl")

    response = hey_bob(sender_player=lobbyboy)
    assert response.status_code == 403  # bob is still at a table, so we can't talk
    assert b"already seated" in response.content

    response = hey_bob(target=lobbygirl, sender_player=lobbyboy)
    assert response.status_code == 200


def test_only_recipient_can_read_messages(usual_setup, settings):
    module_name, class_name = settings.EVENTSTREAM_CHANNELMANAGER_CLASS.rsplit(".", maxsplit=1)
    cm = getattr(importlib.import_module(module_name), class_name)()

    Bob = Player.objects.get_by_name("Bob")
    Ted = Player.objects.get_by_name("Ted")
    Carol = Player.objects.get_by_name("Carol")

    channel = Message.channel_name_from_players(Ted, Bob)

    assert cm.can_read_channel(Ted.user, channel)
    assert not cm.can_read_channel(Carol.user, channel)
