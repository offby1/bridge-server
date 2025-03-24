import base64
import importlib
import json
import logging
import re

import pytest
from bridge.card import Suit as libSuit
from bridge.contract import Bid as libBid
from bridge.seat import Seat as libSeat
from django.conf import settings
from django.contrib import auth
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.test import Client
from django.urls import reverse


from .models import (
    Hand,
    Message,
    Player,
    PlayerException,
    Seat,
    SeatException,
    Table,
    Tournament,
)
from .testutils import set_auction_to
from .views import hand, player

logger = logging.getLogger(__name__)


def test_we_gots_a_home_page(db):
    c = Client()
    response = c.get("/", follow=True)
    assert b"Welcome" in response.content


@pytest.fixture
def j_northam(db, everybodys_password):
    u = auth.models.User.objects.create(username="Jeremy Northam", password=everybodys_password)
    return Player.objects.create(user=u)


def test_synthetic_immutability(db) -> None:
    andy = auth.models.User.objects.create(username="Andy Android")
    android = Player.objects.create(allow_bot_to_play_for_me=True, synthetic=True, user=andy)
    android.synthetic = False
    with pytest.raises(ValidationError) as e:
        android.save()
    assert "cannot be changed" in str(e.value)


def test_splitsville_ejects_that_partnership_from_table(usual_setup):
    the_table = Table.objects.first()

    north = the_table.current_hand.modPlayer_by_seat(libSeat.NORTH)
    south = the_table.current_hand.modPlayer_by_seat(libSeat.SOUTH)

    # duh
    assert north.partner == south
    assert south.partner == north

    assert north.current_table is not None
    assert north.current_table == south.current_table

    table_count_before = Table.objects.count()
    assert table_count_before == 1

    east = the_table.current_hand.modPlayer_by_seat(libSeat.EAST)
    west = the_table.current_hand.modPlayer_by_seat(libSeat.WEST)

    north.break_partnership()

    north.refresh_from_db()
    south.refresh_from_db()
    east.refresh_from_db()
    west.refresh_from_db()

    assert north.partner is None
    assert south.partner is None
    assert west.partner == east
    assert east.partner == west

    assert Table.objects.count() == table_count_before

    assert north.current_table is None
    assert south.current_table is None
    assert east.current_table == the_table
    assert west.current_table == the_table


def test_one_partnerships_splitting_does_not_remove_table(usual_setup):
    assert Table.objects.count() == 1
    t = Table.objects.first()
    north = t.current_hand.modPlayer_by_seat(libSeat.NORTH)

    north.break_partnership()
    assert Table.objects.count() == 1


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
    assert re.search(r"href='/player/.*>.*Jeremy Northam.*</a>", link)


def test_only_bob_can_see_bobs_cards_for_all_values_of_bob(usual_setup) -> None:
    t = Table.objects.first()
    assert t is not None
    north = t.current_hand.modPlayer_by_seat(libSeat.NORTH)
    norths_cards = north.dealt_cards()

    client = Client()

    def r():
        return client.get(reverse("app:hand-detail", kwargs={"pk": t.current_hand.pk}), follow=True)

    response = r()
    for c in norths_cards:
        assert c.serialize() not in response.content.decode()

    assert client.login(username=north.name, password=".")

    response = r()
    for c in norths_cards:
        assert c.serialize() in response.content.decode()


def test_legal_cards(usual_setup, rf):
    t = Table.objects.first()
    set_auction_to(libBid(level=1, denomination=libSuit.CLUBS), t.current_hand)
    h = t.current_hand
    declarer = h.declarer
    leader = t.current_hand.modPlayer_by_seat(declarer.seat.lho()).libraryThing()

    client = Client()
    client.login(username=leader.name, password=".")

    response = client.get(reverse("app:hand-detail", kwargs={"pk": t.current_hand.pk}), follow=True)
    assert "disabled" not in response.content.decode()

    # TODO -- play a card, ensure various holdings are now indeed disabled


def test_player_cannot_be_in_two_tables(usual_setup):
    t1 = Table.objects.first()
    north = t1.current_hand.modPlayer_by_seat(libSeat.NORTH)

    t2 = Table.objects.create(tournament=t1.tournament)

    with pytest.raises(SeatException) as e:
        Seat.objects.create(direction=libSeat.EAST.value, table=t2, player=north)
    assert "already seated at" in str(e.value)


def test_cant_just_make_up_directions(j_northam, everybodys_password):
    partner = Player.objects.create(
        user=auth.models.User.objects.create(
            username="partner",
            password=everybodys_password,
        ),
    )
    j_northam.partner_with(partner)

    t = Table.objects.create(tournament=Tournament.objects.create(display_number=1))
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


def quickly_auth_test_client(c: Client, player: Player) -> None:
    # We could also have just done `c.login(username=user, password=".")` but that uses deliberately-slow
    # password-hashing.
    c.get(
        "/three-way-login/",
        headers={
            "Authorization": "Basic "
            + base64.b64encode(f"{player.pk}:{settings.API_SKELETON_KEY}".encode()).decode()
        },  # type: ignore [arg-type]
    )


def test_sending_lobby_messages(usual_setup):
    def say_hey_from(player=None):
        c = Client()

        if player is not None:
            quickly_auth_test_client(c, player)

        return c.post(
            "/send_lobby_message/",
            content_type="application/json",
            data=json.dumps({"message": "hey you"}),
        )

    response = say_hey_from()
    match response.status_code:  # I'm honestly not sure which of these is correct :-|
        case 403:
            assert response.content == b"Go away, anonymous scoundrel"
        case 302:
            print(vars(response))
        case _:
            msg = f"OK, {response.status_code=} makes no sense"
            raise AssertionError(msg)

    t = Table.objects.first()
    response = say_hey_from(player=t.current_hand.modPlayer_by_seat(libSeat.NORTH))

    assert response.status_code == 200


def test_sending_player_messages(usual_setup, rf, everybodys_password):
    t = Table.objects.first()
    north = t.current_hand.modPlayer_by_seat(libSeat.NORTH)

    def hey_bob(*, target=None, sender_player=None) -> HttpResponse:
        c = Client()

        if target is None:
            target = north

        if sender_player is not None:
            quickly_auth_test_client(c, sender_player)

        return c.post(
            reverse("app:send_player_message", args=[target.pk]),
            data={"message": "hey you"},
        )

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


def test_only_recipient_can_read_messages(usual_setup):
    module_name, class_name = settings.EVENTSTREAM_CHANNELMANAGER_CLASS.rsplit(".", maxsplit=1)
    cm = getattr(importlib.import_module(module_name), class_name)()

    t = Table.objects.first()
    Bob, Ted, Carol, _ = t.current_hand.players_by_direction.values()

    channel = Message.channel_name_from_players(Ted, Bob)

    assert cm.can_read_channel(Ted.user, channel)
    assert not cm.can_read_channel(Carol.user, channel)


def test_seat_ordering(usual_setup):
    t = Table.objects.first()
    assert " ".join([t[0] for t in t.as_tuples()]) == "North East South West"


def test_splitsville_side_effects(usual_setup, rf, monkeypatch):
    t = Table.objects.first()
    north = t.current_hand.modPlayer_by_seat(libSeat.NORTH)
    assert north.partner is not None
    north_pk = north.pk
    north_partner_pk = north.partner.pk

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

    assert set(the_kwargs["data"]["split"]) == {north_pk, north_partner_pk}

    assert response.status_code == 302

    north.refresh_from_db()
    assert north.partner is None

    # Now do it again -- bob ain't got no partner no mo, so we should get an error.
    response = player.player_detail_view(request, north.pk)
    assert 400 <= response.status_code <= 499

    assert b"cannot" in response.content.lower()
    assert b"partner" in response.content.lower()

    assert len(send_event_kwargs_log) == 0


def test_splitsville_prevents_others_at_table_from_playing(usual_setup) -> None:
    t = Table.objects.first()
    assert t is not None

    h: Hand = t.current_hand
    assert h.player_who_may_call is not None
    north = h.modPlayer_by_seat(libSeat.NORTH)
    north.break_partnership()
    h = Hand.objects.get(pk=h.pk)
    assert h.player_who_may_call is None
    assert h.player_who_may_play is None


def test_no_bogus_tables(usual_setup):
    count_before = Table.objects.count()
    with pytest.raises(SeatException):
        Table.objects.create_with_two_partnerships(
            p1=Player.objects.get_by_name("Jeremy Northam"),
            p2=Player.objects.get_by_name("Clint Eastwood"),
            tournament=Tournament.objects.first(),
        )
    count_after = Table.objects.count()

    assert count_after == count_before


def test__three_by_three_trick_display_context_for_table(usual_setup, rf) -> None:
    request = rf.get("/woteva/")
    t = Table.objects.first()

    # Nobody done played nothin'
    assert t is not None
    assert not t.current_hand.current_trick

    set_auction_to(libBid(level=1, denomination=libSuit.DIAMONDS), t.current_hand)
    h = t.current_hand
    declarer = h.declarer

    # TODO -- add a "lho" method to model.Player
    first_players_seat = declarer.seat.lho()
    first_player = t.current_hand.modPlayer_by_seat(first_players_seat)
    first_players_cards = first_player.dealt_cards()

    first_card = first_players_cards[0]

    h.add_play_from_player(player=first_player.libraryThing(), card=first_card)
    t = Table.objects.first()
    h = t.current_hand

    expected_cards_by_direction = {dir_.value: "__" for dir_ in libSeat}
    for tt in h.current_trick:
        expected_cards_by_direction[tt.seat.value] = tt.card.serialize()

    ya = hand._three_by_three_trick_display_context_for_hand(request, h, xscript=h.get_xscript())
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
