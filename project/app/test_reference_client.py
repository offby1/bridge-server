"""Contract tests for the API, driven through the reference client.

These exist twice over: to check the API keeps its promises, and to check that
`app/reference_client.py` -- the thing we hand somebody who wants to write their own
bot -- actually works. An example nobody runs rots; this one fails the build.

Only the HTTP half is covered here. Reading events as they arrive needs a real ASGI
server, because `live_server` is WSGI and django-eventstream yields async iterables;
see docs/README.sse.md.
"""

import pytest
from pytest_django.live_server_helper import LiveServer

from app.models import Hand, Player
from app.reference_client import BridgeClient, BridgeClientError
from bridge.contract import Bid as libBid

PASSWORD = "sekrit"


@pytest.fixture
def declarer_client(
    usual_setup: Hand, live_server: LiveServer
) -> tuple[BridgeClient, Player, Hand]:
    """A logged-in client for whoever the auction is waiting on."""
    hand = usual_setup
    player = hand.player_who_may_call
    assert player is not None, "This fixture's auction should be waiting for somebody"

    user = player.user
    user.set_password(PASSWORD)
    user.save()

    client = BridgeClient(live_server.url)
    client.log_in(user.username, PASSWORD)
    return client, player, hand


@pytest.mark.django_db
def test_logging_in_tells_us_who_we_are(usual_setup: Hand, live_server: LiveServer) -> None:
    player = Player.objects.first()
    assert player is not None
    player.user.set_password(PASSWORD)
    player.user.save()

    client = BridgeClient(live_server.url)
    me = client.log_in(player.user.username, PASSWORD)

    assert me["player_pk"] == player.pk
    assert client.player_pk == player.pk


@pytest.mark.django_db
def test_a_wrong_password_raises_rather_than_looking_like_success(
    usual_setup: Hand, live_server: LiveServer
) -> None:
    player = Player.objects.first()
    assert player is not None
    player.user.set_password(PASSWORD)
    player.user.save()

    client = BridgeClient(live_server.url)

    with pytest.raises(BridgeClientError):
        client.log_in(player.user.username, "not the password")


@pytest.mark.django_db
def test_a_hand_arrives_in_the_documented_shape(
    declarer_client: tuple[BridgeClient, Player, Hand],
) -> None:
    client, _player, hand = declarer_client

    body = client.hand(hand.pk)

    assert body["board"] == hand.board.display_number
    assert body["table"] == hand.table_display_number
    assert body["tournament"] == hand.board.tournament.display_number
    assert "xscript" in body, "The transcript is the whole point of this endpoint"


@pytest.mark.django_db
def test_a_call_we_make_shows_up_when_we_read_the_hand_back(
    declarer_client: tuple[BridgeClient, Player, Hand],
) -> None:
    """The round trip a bot actually performs: act, then re-read to confirm."""
    client, player, hand = declarer_client
    calls_before = client.hand(hand.pk)["xscript"]["auction"]["player_calls"]

    client.call("Pass")

    calls_after = client.hand(hand.pk)["xscript"]["auction"]["player_calls"]

    assert calls_after[:-1] == calls_before, "The calls we already knew about should be unchanged"
    assert len(calls_after) == len(calls_before) + 1, "Exactly one call happened"
    assert libBid.from_python(s=calls_after[-1]["call"]) == libBid.deserialize("Pass"), (
        "and it is the Pass we just made"
    )
    assert calls_after[-1]["player"]["name"] == player.name, "attributed to us"


@pytest.mark.django_db
def test_calling_out_of_turn_raises(
    declarer_client: tuple[BridgeClient, Player, Hand],
) -> None:
    """A client that ignores whose turn it is should find out, loudly.

    Two passes in a row from the same player means the second one isn't ours to make.
    """
    client, _player, _hand = declarer_client
    client.call("Pass")

    with pytest.raises(BridgeClientError):
        client.call("Pass")


@pytest.mark.django_db
def test_re_reading_the_hand_is_how_a_client_catches_up(
    declarer_client: tuple[BridgeClient, Player, Hand],
) -> None:
    """The recovery story we document, exercised.

    Something happens that the client wasn't told about -- here, another player calls --
    and the client discovers it by asking, not by replaying events it missed.
    """
    client, _player, hand = declarer_client
    calls_before = client.hand(hand.pk)["xscript"]["auction"]["player_calls"]

    hand.add_call(call=libBid.deserialize("Pass"))

    calls_after = client.hand(hand.pk)["xscript"]["auction"]["player_calls"]

    assert calls_after[:-1] == calls_before, "The calls we already knew about should be unchanged"
    assert len(calls_after) == len(calls_before) + 1, "Exactly one call happened"
    assert libBid.from_python(s=calls_after[-1]["call"]) == libBid.deserialize("Pass"), (
        "and the one that happened is the Pass we made behind the client's back"
    )
