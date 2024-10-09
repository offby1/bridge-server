import importlib
import json

import pytest
from bridge.card import Suit as libSuit
from bridge.contract import Bid as libBid
from bridge.seat import Seat as libSeat
from django.contrib import auth
from django.contrib.auth.models import AnonymousUser
from django.db import IntegrityError
from django.test import Client
from django.urls import reverse

from .models import Message, Player, PlayerException, Seat, SeatException, Table
from .testutils import set_auction_to
from .views import lobby, player, table


def test_we_gots_a_home_page():
    c = Client()
    response = c.get("/", follow=True)
    assert b"Welcome" in response.content


@pytest.fixture
def j_northam(db, everybodys_password):
    u = auth.models.User.objects.create(username="Jeremy Northam", password=everybodys_password)
    return Player.objects.create(user=u)


def test_splitsville_ejects_everyone_from_table(usual_setup):
    table = Table.objects.first()

    north = table.current_hand.modPlayer_by_seat(libSeat.NORTH)
    south = table.current_hand.modPlayer_by_seat(libSeat.SOUTH)

    # duh
    assert north.partner == south
    assert south.partner == north

    assert north.table is not None
    assert north.table == south.table

    table_count_before = Table.objects.count()
    assert table_count_before == 1

    east = table.current_hand.modPlayer_by_seat(libSeat.EAST)
    west = table.current_hand.modPlayer_by_seat(libSeat.WEST)

    north.break_partnership()

    north = Player.objects.get(pk=north.pk)
    south = Player.objects.get(pk=south.pk)
    east = Player.objects.get(pk=east.pk)
    west = Player.objects.get(pk=west.pk)

    assert north.partner is None
    assert south.partner is None
    assert west.partner == east
    assert east.partner == west

    assert Table.objects.count() == table_count_before - 1

    assert north.table is None
    assert south.table is None
    assert east.table is None
    assert west.table is None


def test_one_partnerships_splitting_removes_table(usual_setup):
    assert Table.objects.count() == 1
    t = Table.objects.first()
    north = t.current_hand.modPlayer_by_seat(libSeat.NORTH)

    north.break_partnership()
    assert Table.objects.count() == 0


def test_splitsville_non_seated_partnership(j_northam, everybodys_password):
    Alice = Player.objects.create(
        user=auth.models.User.objects.create(username="Alice", password=everybodys_password),
    )
    Alice.partner_with(j_northam)

    Alice.break_partnership()
    j_northam.refresh_from_db()
    assert j_northam.partner is None


def test_player_names_are_links_to_detail_page(usual_setup):
    p = Player.objects.get_by_name("Jeremy Northam")

    link = p.as_link()
    assert ">Jeremy Northam" in link
    assert "href='/player/" in link


def test_only_bob_can_see_bobs_cards_for_all_values_of_bob(usual_setup) -> None:
    t = Table.objects.first()
    assert t is not None
    north = t.current_hand.modPlayer_by_seat(libSeat.NORTH)
    norths_cards = north.libraryThing.hand.cards

    client = Client()

    def r():
        return client.get(reverse("app:table-detail", kwargs={"pk": t.pk}), follow=True)

    response = r()
    for c in norths_cards:
        assert c.serialize() not in response.content.decode()

    client.login(username=north.name, password=".")

    response = r()
    for c in norths_cards:
        assert c.serialize() in response.content.decode()


def test_legal_cards(usual_setup, rf, settings):
    t = Table.objects.first()
    t = set_auction_to(libBid(level=1, denomination=libSuit.CLUBS), t)
    h = t.current_hand
    declarer = h.declarer
    leader = t.current_hand.modPlayer_by_seat(declarer.seat.lho()).libraryThing

    client = Client()
    client.login(username=leader.name, password=".")

    response = client.get(reverse("app:table-detail", kwargs={"pk": t.pk}), follow=True)
    assert "disabled" not in response.content.decode()

    # TODO -- play a card, ensure various holdings are now indeed disabled


def test_player_cannot_be_at_two_seats(usual_setup):
    t = Table.objects.first()

    # Try to sneak Jeremy into Esther's seat!
    # We use "update" in order to circumvent the various checks in the "save" method, which otherwise would trigger.
    with pytest.raises(IntegrityError):
        Seat.objects.filter(
            direction=libSeat.EAST.value,
            table=t,
        ).update(
            player=t.current_hand.modPlayer_by_seat(libSeat.NORTH),
        )


def test_player_cannot_be_in_two_tables(usual_setup):
    t1 = Table.objects.first()
    north = t1.modPlayer_by_seat(libSeat.NORTH)

    # We use "update" in order to circumvent the various checks in the "save" method, which otherwise would trigger.
    t2 = Table.objects.create()

    with pytest.raises(SeatException):
        Seat.objects.create(direction=libSeat.EAST.value, table=t2, player=north)


def test_cant_just_make_up_directions(j_northam, everybodys_password):
    partner = Player.objects.create(
        user=auth.models.User.objects.create(
            username="partner",
            password=everybodys_password,
        ),
    )
    j_northam.partner_with(partner)

    t = Table.objects.create()
    with pytest.raises(Exception) as e:
        Seat.objects.create(direction=1234, player=j_northam, table=t)

    assert "app_seat_direction_valid" in str(e.value)


def test_breaking_up_is_hard_to_do(usual_setup):
    t = Table.objects.first()
    North = t.current_hand.modPlayer_by_seat(libSeat.NORTH)
    East = t.current_hand.modPlayer_by_seat(libSeat.EAST)
    South = t.current_hand.modPlayer_by_seat(libSeat.SOUTH)
    West = t.current_hand.modPlayer_by_seat(libSeat.WEST)

    assert North.partner == South
    assert South.partner == North

    # No exception because Bob is already partnered with Ted, so an exception would serve no purpose.
    North.partner_with(South)

    with pytest.raises(PlayerException) as e:
        North.partner_with(East)
    assert "already partnered with" in str(e.value)

    North.break_partnership()
    North.refresh_from_db()
    South.refresh_from_db()
    assert North.partner is None
    assert South.partner is None

    # No exception because Bob is single
    West.break_partnership()
    East.refresh_from_db()
    North.partner_with(East)


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

    t = Table.objects.first()
    response = lobby.send_lobby_message(
        say_hey(user=t.current_hand.modPlayer_by_seat(libSeat.NORTH).user)
    )
    assert response.status_code == 200


def test_sending_player_messages(usual_setup, rf, everybodys_password):
    t = Table.objects.first()
    north = t.current_hand.modPlayer_by_seat(libSeat.NORTH)

    def hey_bob(*, target=None, sender_player=None):
        if target is None:
            target = north

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

    response = hey_bob(sender_player=t.current_hand.modPlayer_by_seat(libSeat.SOUTH))
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

    t = Table.objects.first()
    Bob, Ted, Carol, _ = t.players_by_direction.values()

    channel = Message.channel_name_from_players(Ted, Bob)

    assert cm.can_read_channel(Ted.user, channel)
    assert not cm.can_read_channel(Carol.user, channel)


def test_seat_ordering(usual_setup):
    t = Table.objects.first()
    assert " ".join([t[0] for t in t.as_tuples()]) == "NORTH EAST SOUTH WEST"


def test_splitsville_side_effects(usual_setup, rf, monkeypatch, settings):
    t = Table.objects.first()
    north = t.current_hand.modPlayer_by_seat(libSeat.NORTH)
    assert north.partner is not None

    request = rf.post(
        "/player_detail_endpoint_whatever_tf_it_is HEY IT TURNS OUT THIS DOESN'T MATTER, WHO KNEW??/",
        data={"action": "splitsville"},
    )

    request.user = north.user

    send_event_kwargs_log = []

    def mock_send_event(*args, **kwargs):
        send_event_kwargs_log.append(kwargs)

    import app.models.player

    monkeypatch.setattr(app.models.player, "send_event", mock_send_event)
    response = player.player_detail_view(request, north.pk)

    assert len(send_event_kwargs_log) == 1
    the_kwargs = send_event_kwargs_log.pop()

    assert the_kwargs["channel"] == "partnerships"
    assert the_kwargs["data"]["joined"] == []

    assert set(the_kwargs["data"]["split"]) == {north.pk, north.partner.pk}

    assert response.status_code == 200

    north.refresh_from_db()
    assert north.partner is None

    # Now do it again -- bob ain't got no partner no mo, so we should get an error.
    response = player.player_detail_view(request, north.pk)
    assert 400 <= response.status_code <= 499

    assert b"cannot" in response.content.lower()
    assert b"partner" in response.content.lower()

    assert len(send_event_kwargs_log) == 0


def test_table_creation(j_northam, rf, everybodys_password):
    players_by_name = {"bob": j_northam}
    sam = Player.objects.create(
        user=auth.models.User.objects.create(
            username="sam",
            password=everybodys_password,
        ),
    )
    players_by_name["sam"] = sam
    sam.partner_with(j_northam)

    assert j_northam.partner is not None

    request = rf.post(
        "/woteva/",
        data={"pk1": j_northam.pk, "pk2": j_northam.pk},
    )

    request.user = j_northam.user
    response = table.details.new_table_for_two_partnerships(request, j_northam.pk, j_northam.pk)
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
        data={"pk1": j_northam.pk, "pk2": players_by_name["tina"].pk},
    )
    request.user = j_northam.user
    response = table.details.new_table_for_two_partnerships(
        request, j_northam.pk, players_by_name["tina"].pk
    )

    assert response.status_code == 302


def test_random_dude_cannot_create_table(usual_setup, rf, everybodys_password):
    t = Table.objects.first()
    Bob, Carol, Ted, Alice = t.players_by_direction.values()

    from app.models import logged_queries

    with logged_queries():
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
        return table.details.new_table_for_two_partnerships(request, Bob.pk, Carol.pk)

    response = seat_em_dano(RandomDude)
    assert response.status_code == 403
    assert b"isn't one of" in response.content

    response = seat_em_dano(Bob)
    assert response.status_code == 302


def test__three_by_three_trick_display_context_for_table(usual_setup, rf):
    request = rf.get("/woteva/")
    t = Table.objects.first()

    # Nobody done played nothin'
    assert not t.current_hand.current_trick

    t = set_auction_to(libBid(level=1, denomination=libSuit.DIAMONDS), t)
    h = t.current_hand
    declarer = h.declarer

    # TODO -- add a "lho" method to model.Player
    first_players_seat = declarer.seat.lho()
    first_player = t.current_hand.modPlayer_by_seat(first_players_seat).libraryThing
    first_players_cards = first_player.hand.cards

    first_card = first_players_cards[0]

    h.add_play_from_player(player=first_player, card=first_card)
    t = Table.objects.first()
    h = t.current_hand

    expected_cards_by_direction = {dir_.value: "__" for dir_ in libSeat}
    for _index, s, modelCard, _is_winner in h.current_trick:
        expected_cards_by_direction[s.value] = modelCard.serialize()

    ya = table.details._three_by_three_trick_display_context_for_table(request, t)
    three_by_three_trick_display_rows = ya["three_by_three_trick_display"]["rows"]

    north_row, east_west_row, south_row = three_by_three_trick_display_rows
    actual_cards_by_direction = {
        libSeat.NORTH.value: north_row[1],
        libSeat.EAST.value: east_west_row[2],
        libSeat.SOUTH.value: south_row[1],
        libSeat.WEST.value: east_west_row[0],
    }

    for direction, actual_html in actual_cards_by_direction.items():
        expected_html = expected_cards_by_direction[direction]
        assert expected_html in actual_html
