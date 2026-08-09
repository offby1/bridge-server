"""Tests for the channel set behind the consolidated `/events/all/` endpoint.

The browser used to open one connection per channel, which exhausted Chrome's six
connections per origin after a few navigations. Now one connection carries everything,
and `MyChannelManager.get_channels_for_request` decides what "everything" means for the
viewer making the request. See README.branch.md.
"""

import pytest
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory

from app.channelmanager import MyChannelManager
from app.models import Hand, Message, Player
from app.sse_channels import SSEChannels


def _channels(*, user, query: str = "", view_kwargs: dict | None = None) -> set[str]:
    request = RequestFactory().get(f"/events/all/?{query}")
    request.user = user
    return MyChannelManager().get_channels_for_request(request, view_kwargs or {})


@pytest.mark.django_db
def test_a_bare_request_gets_the_viewers_own_channels(usual_setup: Hand) -> None:
    player = Player.objects.first()
    assert player is not None

    assert _channels(user=player.user) == {
        SSEChannels.player_html_hand(player.pk),
        SSEChannels.player_bot_checkbox(player.pk),
    }


@pytest.mark.django_db
def test_the_hand_parameter_adds_that_table(usual_setup: Hand) -> None:
    """The hand being viewed is not always the viewer's own, so the page passes it in."""
    hand = usual_setup
    player = next(iter(hand.players()))

    assert SSEChannels.table_html(hand.pk) in _channels(user=player.user, query=f"hand={hand.pk}")


@pytest.mark.django_db
def test_an_unreadable_channel_is_dropped_rather_than_refused(usual_setup: Hand) -> None:
    """One forbidden channel must not cost the viewer every other update.

    `get_events()` raises `EventPermissionError` for the whole request if any requested
    channel is unreadable. On a consolidated connection that would mean a bad `?hand=`
    silently killing the bidding box, the checkbox and chat along with it, so we filter
    the set ourselves instead of asking for channels we know will be refused.
    """
    player = Player.objects.first()
    assert player is not None
    missing_hand_pk = 10_000
    assert not Hand.objects.filter(pk=missing_hand_pk).exists()

    channels = _channels(user=player.user, query=f"hand={missing_hand_pk}")

    assert SSEChannels.table_html(missing_hand_pk) not in channels
    assert SSEChannels.player_bot_checkbox(player.pk) in channels


@pytest.mark.django_db
def test_a_hand_that_is_not_a_primary_key_is_ignored(usual_setup: Hand) -> None:
    """`can_read_channel` waves through any channel it doesn't recognise.

    Its final branch returns True for unrecognised names, so `?hand=abc` would build
    `table:html:abc`, match none of the patterns, and be allowed. Nothing publishes
    there, so this isn't a leak, but subscribing to junk on the say-so of a query
    parameter is not a habit worth having.

    "Not a primary key" rather than "not a number": the check goes through
    `PK_from_str`, so it follows `app/models/types.py` if primary keys ever stop being
    integers.
    """
    player = Player.objects.first()
    assert player is not None

    channels = _channels(user=player.user, query="hand=abc")

    assert not any(c.startswith("table:html:") for c in channels)


@pytest.mark.django_db
def test_the_chat_parameter_adds_the_channel_messages_are_actually_sent_to(
    usual_setup: Hand,
) -> None:
    """A chat channel is `players:<pk>_<pk>`, with no prefix.

    The old endpoint's URL was /events/chat/player-to-player/<channel>/, and it passed
    <channel> through untouched, so the path prefix was never part of the channel name.
    We once prefixed it here, subscribed to a channel nothing publishes to, and got
    silence on the chat log.
    """
    player = Player.objects.first()
    assert player is not None
    assert player.partner is not None
    chat_channel = Message.channel_name_from_players(player, player.partner)

    channels = _channels(user=player.user, query=f"chat={chat_channel}")

    assert chat_channel in channels
    assert not any(c.startswith("chat:") for c in channels)


@pytest.mark.django_db
def test_a_chat_channel_naming_other_players_is_dropped(usual_setup: Hand) -> None:
    """Reading someone else's chat is exactly what `can_read_channel` exists to stop."""
    player = Player.objects.first()
    assert player is not None
    others = list(Player.objects.exclude(pk=player.pk)[:2])
    assert len(others) == 2
    someone_elses = Message.channel_name_from_players(others[0], others[1])

    assert someone_elses not in _channels(user=player.user, query=f"chat={someone_elses}")


@pytest.mark.django_db
def test_a_chat_channel_that_is_not_a_channel_name_is_ignored(usual_setup: Hand) -> None:
    """Junk must not reach `can_read_channel`'s catch-all, which returns True."""
    player = Player.objects.first()
    assert player is not None

    assert _channels(user=player.user, query="chat=nonsense") == _channels(user=player.user)


@pytest.mark.django_db
def test_the_old_per_channel_endpoints_still_work(usual_setup: Hand) -> None:
    """They name their channel in the URLconf, and we defer to django-eventstream."""
    player = Player.objects.first()
    assert player is not None

    assert _channels(user=player.user, view_kwargs={"channels": ["lobby"]}) == {"lobby"}


@pytest.mark.django_db
def test_anonymous_visitors_get_nothing(usual_setup: Hand) -> None:
    """`can_read_channel` already refuses anyone without a player.

    When we let logged-out users watch games, this is one of the places that changes.
    """
    assert _channels(user=AnonymousUser()) == set()
