"""Tests for the channel set behind the consolidated `/events/all/` endpoint.

The browser used to open one connection per channel, which exhausted Chrome's six
connections per origin after a few navigations. Now one connection carries everything,
and `MyChannelManager.get_channels_for_request` decides what "everything" means for the
viewer making the request. See README.branch.md.
"""

import inspect
from typing import cast

import pytest
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory

from app.channelmanager import MyChannelManager
from app.models import Hand, Message, Player
from app.models.utils import UserMitPlaya
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
    """`?hand=abc` would build `table:html:abc`, which is nobody's channel.

    `can_read_channel` denies unrecognised names now, so this is belt and braces --
    but it is cheaper to not ask for a junk channel than to be refused one, and when
    this check was written the catch-all still allowed them.

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
    """Don't ask for a channel we know is junk, even though it would now be refused."""
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
def test_can_read_channel_denies_names_it_does_not_recognise(usual_setup: Hand) -> None:
    """The catch-all used to allow them, which cost us two bugs on /events/all/."""
    player = Player.objects.first()
    assert player is not None

    assert not MyChannelManager().can_read_channel(
        cast(UserMitPlaya, player.user), "no-such-channel"
    )


@pytest.mark.django_db
def test_every_channel_we_publish_to_is_readable_by_its_audience(usual_setup: Hand) -> None:
    """Deny-by-default is only safe if the allow list is complete.

    If a channel we actually `send_event` to isn't recognised here, subscribers get
    silence, and on the consolidated connection one such channel takes the whole stream
    down with an EventPermissionError.
    """
    hand = usual_setup
    player = next(iter(hand.players()))
    assert player.partner is not None
    manager = MyChannelManager()

    # Walk SSEChannels rather than listing it, so a channel added later is covered
    # without anyone having to remember this test. Constants are channel names; the rest
    # are functions, and their parameter names say which primary key they want.
    available_pks = {"player_pk": player.pk, "hand_pk": hand.pk}
    channels = []
    for name in vars(SSEChannels):
        if name.startswith("_"):
            continue
        member = getattr(SSEChannels, name)
        if isinstance(member, str):
            channels.append(member)
            continue
        wanted = inspect.signature(member).parameters
        unknown = set(wanted) - set(available_pks)
        assert not unknown, (
            f"SSEChannels.{name} wants {sorted(unknown)}, which this test can't supply. "
            f"Add it to available_pks."
        )
        channels.append(member(**{p: available_pks[p] for p in wanted}))

    # Chat lives on Message, which owns the `players:<pk>_<pk>` format.
    channels.append(Message.channel_name_from_players(player, player.partner))

    assert len(channels) >= 8, f"Only found {len(channels)}; has SSEChannels moved?"
    for channel in channels:
        assert manager.can_read_channel(cast(UserMitPlaya, player.user), channel), channel


@pytest.mark.django_db
def test_anonymous_visitors_get_nothing(usual_setup: Hand) -> None:
    """`can_read_channel` already refuses anyone without a player.

    When we let logged-out users watch games, this is one of the places that changes.
    """
    assert _channels(user=AnonymousUser()) == set()
