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
    Board,
    Hand,
    HandError,
    Message,
    Player,
    PlayerException,
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


def test_splitsville_doesnt_affect_opponents(usual_setup: Hand):
    h = usual_setup

    north = h.modPlayer_by_seat(libSeat.NORTH)
    south = h.modPlayer_by_seat(libSeat.SOUTH)

    # duh
    assert north.partner == south
    assert south.partner == north

    east = h.modPlayer_by_seat(libSeat.EAST)
    west = h.modPlayer_by_seat(libSeat.WEST)

    north.break_partnership()

    north.refresh_from_db()
    south.refresh_from_db()
    east.refresh_from_db()
    west.refresh_from_db()

    assert north.partner is None
    assert south.partner is None
    assert west.partner == east
    assert east.partner == west


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


def test_only_bob_can_see_bobs_cards_for_all_values_of_bob(usual_setup: Hand) -> None:
    h = usual_setup
    north = h.modPlayer_by_seat(libSeat.NORTH)
    norths_cards = north.dealt_cards()

    client = Client()

    def r():
        return client.get(reverse("app:hand-detail", kwargs={"pk": h.pk}), follow=True)

    response = r()
    for c in norths_cards:
        assert c.serialize() not in response.content.decode()

    assert client.login(username=north.name, password=".")

    response = r()
    for c in norths_cards:
        assert c.serialize() in response.content.decode()


def test_legal_cards(usual_setup: Hand, rf) -> None:
    h = usual_setup
    set_auction_to(libBid(level=1, denomination=libSuit.CLUBS), h)

    declarer = h.declarer
    assert declarer is not None
    leader = h.modPlayer_by_seat(declarer.seat.lho()).libraryThing()

    client = Client()
    client.login(username=leader.name, password=".")

    response = client.get(reverse("app:hand-detail", kwargs={"pk": h.pk}), follow=True)
    assert "disabled" not in response.content.decode()

    # TODO -- play a card, ensure various holdings are now indeed disabled


def test_player_cannot_be_in_two_incomplete_hands(usual_setup: Hand) -> None:
    h1 = usual_setup

    with pytest.raises(HandError) as e:
        Hand.objects.create(
            board=Board.objects.get_or_create_from_display_number(
                display_number=Board.objects.count() + 1,
                group="A",
                tournament=h1.tournament,
            ),
            North=h1.North,
            East=h1.East,
            South=h1.South,
            West=h1.West,
        )

    assert "Cannot seat" in str(e.value)


def test_breaking_up_is_hard_to_do(usual_setup: Hand) -> None:
    h = usual_setup

    North = h.modPlayer_by_seat(libSeat.NORTH)
    East = h.modPlayer_by_seat(libSeat.EAST)
    South = h.modPlayer_by_seat(libSeat.SOUTH)
    West = h.modPlayer_by_seat(libSeat.WEST)

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


def test_sending_lobby_messages(usual_setup: Hand) -> None:
    h = usual_setup

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

    response = say_hey_from(player=h.modPlayer_by_seat(libSeat.NORTH))

    assert response.status_code == 200


def test_sending_player_messages(usual_setup: Hand, rf, everybodys_password):
    h = usual_setup
    north = h.modPlayer_by_seat(libSeat.NORTH)

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

    response = hey_bob(sender_player=h.modPlayer_by_seat(libSeat.SOUTH))
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


def test_only_recipient_can_read_messages(usual_setup: Hand):
    h = usual_setup
    module_name, class_name = settings.EVENTSTREAM_CHANNELMANAGER_CLASS.rsplit(".", maxsplit=1)
    cm = getattr(importlib.import_module(module_name), class_name)()

    Bob, Ted, Carol, _ = h.players_by_direction_letter.values()

    channel = Message.channel_name_from_players(Ted, Bob)

    assert cm.can_read_channel(Ted.user, channel)
    assert not cm.can_read_channel(Carol.user, channel)


def test_splitsville_side_effects(usual_setup: Hand, rf, monkeypatch) -> None:
    h = usual_setup
    north = h.modPlayer_by_seat(libSeat.NORTH)
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


def test_splitsville_prevents_others_at_table_from_playing(usual_setup: Hand) -> None:
    h = usual_setup
    assert h.player_who_may_call is not None
    north = h.modPlayer_by_seat(libSeat.NORTH)
    north.break_partnership()
    h = Hand.objects.get(pk=h.pk)
    assert h.player_who_may_call is None
    assert h.player_who_may_play is None


def test__three_by_three_trick_display_context_for_table(usual_setup: Hand, rf) -> None:
    request = rf.get("/woteva/")
    h = usual_setup

    # Nobody done played nothin'
    assert not h.current_trick

    set_auction_to(libBid(level=1, denomination=libSuit.DIAMONDS), h)
    declarer = h.declarer
    assert declarer is not None

    # TODO -- add a "lho" method to model.Player
    first_players_seat = declarer.seat.lho()
    first_player = h.modPlayer_by_seat(first_players_seat)
    first_players_cards = first_player.dealt_cards()

    first_card = first_players_cards[0]

    h.add_play_from_player(player=first_player.libraryThing(), card=first_card)

    expected_cards_by_direction = {dir_.value: "__" for dir_ in libSeat}
    assert h.current_trick is not None
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
