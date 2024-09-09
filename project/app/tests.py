import importlib
import json

import bridge.seat
import pytest
from bridge.card import Suit as libSuit
from bridge.contract import Bid as libBid
from bridge.seat import Seat as libSeat
from django.contrib import auth
from django.contrib.auth.models import AnonymousUser
from django.db import IntegrityError
from django.test import Client
from django.urls import reverse

from .models import Message, Player, PlayerException, Seat, Table
from .testutils import set_auction_to
from .views import lobby, player, table


def test_we_gots_a_home_page():
    c = Client()
    response = c.get("/")
    assert b"Welcome" in response.content


@pytest.fixture
def bob(db, everybodys_password):
    u = auth.models.User.objects.create(username="Bob", password=everybodys_password)
    return Player.objects.create(user=u)


def test_all_seated_players_have_partners(usual_setup):
    for p in Table.objects.first().players_by_direction.values():
        assert p.partner is not None
        p.partner = None
        with pytest.raises(Exception) as e:
            p.save()
        assert "but has no partner" in str(e.value)
        p.seat = None
        p.save()


def test_splitsville_ejects_everyone_from_table(usual_setup):
    table_count_before = Table.objects.count()

    Bob = Player.objects.get_by_name("Bob")
    Ted = Player.objects.get_by_name("Ted")

    # duh
    assert Bob.partner == Ted
    assert Ted.partner == Bob

    assert Bob.table is not None
    assert Bob.table == Ted.table

    Bob.break_partnership()
    Bob.refresh_from_db()
    Ted.refresh_from_db()
    assert Bob.partner is None
    assert Bob.partner == Ted.partner

    assert Bob.table is None
    assert Ted.table is None

    assert Table.objects.count() == table_count_before - 1

    Carol = Player.objects.get_by_name("Carol")
    Alice = Player.objects.get_by_name("Alice")
    assert Carol.table is None
    assert Alice.table is None


def test_both_table_partnerships_splitting_removes_table(usual_setup):
    assert Table.objects.count() == 1

    Bob = Player.objects.get_by_name("Bob")
    Carol = Player.objects.get_by_name("Carol")

    Bob.break_partnership()
    assert Table.objects.count() == 0

    Carol.break_partnership()
    assert Table.objects.count() == 0


def test_splitsville_non_seated_partnership(bob, everybodys_password):
    Alice = Player.objects.create(
        user=auth.models.User.objects.create(username="Alice", password=everybodys_password),
    )
    Alice.partner_with(bob)

    Alice.break_partnership()
    bob.refresh_from_db()
    assert bob.partner is None


def test_player_names_are_links_to_detail_page(usual_setup):
    p = Player.objects.get_by_name("Bob")

    link = p.as_link()
    assert ">Bob" in link
    assert "href='/player/" in link


def test_only_bob_can_see_bobs_cards(usual_setup):
    t = Table.objects.first()
    bob = Player.objects.get_by_name("Bob")
    bobs_cards = bob.libraryThing.hand.cards

    client = Client()

    def r():
        return client.get(reverse("app:table-detail", kwargs={"pk": t.pk}), follow=True)

    response = r()
    for c in bobs_cards:
        assert c.serialize() not in response.content.decode()

    client.login(username="Bob", password=".")

    response = r()
    for c in bobs_cards:
        assert c.serialize() in response.content.decode()


def test_legal_cards(usual_setup, rf):
    t = Table.objects.first()
    set_auction_to(libBid(level=1, denomination=libSuit.CLUBS), t)
    h = t.current_handrecord
    declarer = h.declarer
    leader = t[declarer.seat.lho()]

    client = Client()
    client.login(username=leader.name, password=".")

    def r():
        return client.get(reverse("app:table-detail", kwargs={"pk": t.pk}), follow=True)

    response = r()
    assert "disabled" not in response.content.decode()

    # TODO -- play a card, ensure various holdings are now indeed disabled


def test_player_cannot_be_at_two_seats(usual_setup):
    t = Table.objects.first()

    # Try to sneak Bob into Carol's seat!
    # We use "update" in order to circumvent the various checks in the "save" method, which otherwise would trigger.
    with pytest.raises(IntegrityError):
        Seat.objects.filter(
            direction=bridge.seat.Seat.EAST.value,
            table=t,
        ).update(
            player=Player.objects.get_by_name("Bob"),
        )


def test_player_cannot_be_in_two_tables(usual_setup):
    bob = Player.objects.get_by_name("Bob")

    # We use "update" in order to circumvent the various checks in the "save" method, which otherwise would trigger.
    t2 = Table.objects.create()

    s = Seat.objects.create(direction=bridge.seat.Seat.EAST.value, table=t2)
    with pytest.raises(IntegrityError):
        Seat.objects.filter(pk=s.pk).update(player=bob)


def test_cant_just_make_up_directions(bob, everybodys_password):
    partner = Player.objects.create(
        user=auth.models.User.objects.create(
            username="partner",
            password=everybodys_password,
        ),
    )
    bob.partner_with(partner)

    t = Table.objects.create()
    with pytest.raises(Exception) as e:
        Seat.objects.create(direction=1234, player=bob, table=t)

    assert "app_seat_direction_valid" in str(e.value)


def test_breaking_up_is_hard_to_do(usual_setup):
    Bob = Player.objects.get_by_name("Bob")
    Carol = Player.objects.get_by_name("Carol")
    Ted = Player.objects.get_by_name("Ted")
    Alice = Player.objects.get_by_name("Alice")

    assert Bob.partner == Ted
    assert Ted.partner == Bob

    # No exception because Bob is already partnered with Ted, so an exception would serve no purpose.
    Bob.partner_with(Ted)

    with pytest.raises(PlayerException) as e:
        Bob.partner_with(Carol)
    assert "already partnered with" in str(e.value)

    Bob.break_partnership()
    Bob.refresh_from_db()
    Ted.refresh_from_db()
    assert Bob.partner is None
    assert Ted.partner is None

    # No exception because Bob is single
    Alice.break_partnership()
    Carol.refresh_from_db()
    Bob.partner_with(Carol)


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
            data=json.dumps({"message": "hey you"}),
        )
        request.user = user
        return request

    response = lobby.send_lobby_message(say_hey())
    assert response.status_code == 403  # client isn't authenticated
    assert response.content == b"Go away, anonymous scoundrel"

    response = lobby.send_lobby_message(say_hey(user=Player.objects.get_by_name("Bob").user))
    assert response.status_code == 200


def test_sending_player_messages(usual_setup, rf, everybodys_password):
    bob = Player.objects.get_by_name("Bob")

    def hey_bob(*, target=None, sender_player=None):
        if target is None:
            target = bob

        user = AnonymousUser() if sender_player is None else sender_player.user

        request = rf.post(
            reverse("app:send_player_message", args=[target.pk]),
            data={"message": "hey you"},
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
            user=auth.models.User.objects.create(
                username=n,
                password=everybodys_password,
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


def test_seat_ordering(usual_setup):
    t = Table.objects.first()
    assert " ".join([t[0] for t in t.as_tuples()]) == "NORTH EAST SOUTH WEST"


def test_splitsville_side_effects(usual_setup, rf, monkeypatch, settings):
    Bob = Player.objects.get_by_name("Bob")
    assert Bob.partner is not None

    request = rf.post(
        "/player_detail_endpoint_whatever_tf_it_is HEY IT TURNS OUT THIS DOESN'T MATTER, WHO KNEW??/",
        data={"action": "splitsville"},
    )

    request.user = Bob.user

    send_event_kwargs_log = []

    def mock_send_event(*args, **kwargs):
        send_event_kwargs_log.append(kwargs)

    import app.models.player

    monkeypatch.setattr(app.models.player, "send_event", mock_send_event)
    response = player.player_detail_view(request, Bob.pk)

    assert len(send_event_kwargs_log) == 1
    the_kwargs = send_event_kwargs_log.pop()

    assert the_kwargs["channel"] == "partnerships"
    assert the_kwargs["data"]["joined"] == []

    assert set(the_kwargs["data"]["split"]) == {Bob.pk, Bob.partner.pk}

    assert response.status_code == 200

    Bob.refresh_from_db()
    assert Bob.partner is None

    # Now do it again -- bob ain't got no partner no mo, so we should get an error.
    response = player.player_detail_view(request, Bob.pk)
    assert 400 <= response.status_code <= 499

    assert b"cannot" in response.content.lower()
    assert b"partner" in response.content.lower()

    assert len(send_event_kwargs_log) == 0


def test_table_creation(bob, rf, everybodys_password):
    players_by_name = {"bob": bob}
    sam = Player.objects.create(
        user=auth.models.User.objects.create(
            username="sam",
            password=everybodys_password,
        ),
    )
    players_by_name["sam"] = sam
    sam.partner_with(bob)

    assert bob.partner is not None

    request = rf.post(
        "/woteva/",
        data={"pk1": bob.pk, "pk2": bob.pk},
    )

    request.user = bob.user
    response = table.new_table_for_two_partnerships(request, bob.pk, bob.pk)
    assert response.status_code == 403
    assert b"four distinct" in response.content

    for name in ("tina", "tony"):
        p = Player.objects.create(
            user=auth.models.User.objects.create(
                username=name,
                password=name,
            ),
        )
        players_by_name[name] = p

    players_by_name["tina"].partner_with(players_by_name["tony"])

    request = rf.post(
        "/woteva/",
        data={"pk1": bob.pk, "pk2": players_by_name["tina"].pk},
    )
    request.user = bob.user
    response = table.new_table_for_two_partnerships(request, bob.pk, players_by_name["tina"].pk)

    assert response.status_code == 302


def test_random_dude_cannot_create_table(usual_setup, rf, everybodys_password):
    Bob = Player.objects.get_by_name("Bob")
    Ted = Player.objects.get_by_name("Ted")
    Carol = Player.objects.get_by_name("Carol")
    Alice = Player.objects.get_by_name("Alice")

    Bob.break_partnership()
    Bob.partner_with(Ted)
    Carol.break_partnership()
    Carol.partner_with(Alice)

    assert Table.objects.count() == 0

    # OK now we got four players ready to sit at a table.

    RandomDude = Player.objects.create(
        user=auth.models.User.objects.create(
            username="J.Random Hacker",
            password=everybodys_password,
        ),
    )

    def seat_em_dano(player=None):
        request = rf.post("/woteva/")

        request.user = player.user
        return table.new_table_for_two_partnerships(request, Bob.pk, Carol.pk)

    response = seat_em_dano(RandomDude)
    assert response.status_code == 403
    assert b"isn't one of" in response.content

    response = seat_em_dano(Bob)
    assert response.status_code == 302


def test__three_by_three_trick_display_context_for_table(usual_setup, rf):
    request = rf.get("/woteva/")
    t = Table.objects.first()

    h = t.current_handrecord

    # Nobody done played nothin'
    assert not h.current_trick

    set_auction_to(libBid(level=1, denomination=libSuit.DIAMONDS), t)
    declarer = h.declarer

    # TODO -- add a "lho" method to model.Player
    first_players_seat = declarer.seat.lho()
    first_player = t[first_players_seat]
    first_players_cards = first_player.hand.cards

    first_card = first_players_cards[0]
    h.add_play_from_player(player=first_player, card=first_card)

    expected_cards_by_direction = {dir_.value: "" for dir_ in libSeat}
    for _index, s, modelCard in h.current_trick:
        expected_cards_by_direction[s.value] = modelCard.serialize()

    ya = table._three_by_three_trick_display_context_for_table(request, t)
    north_row, east_west_row, south_row = ya["three_by_three_trick_display"]["rows"]
    actual_cards_by_direction = {
        libSeat.NORTH.value: north_row[1],
        libSeat.EAST.value: east_west_row[2],
        libSeat.SOUTH.value: south_row[1],
        libSeat.WEST.value: east_west_row[0],
    }
    assert actual_cards_by_direction == expected_cards_by_direction
