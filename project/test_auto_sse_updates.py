from unittest.mock import patch

import app.broadcast
import pytest
from app.models import Player
from app.sse_events import SSEEventTypes
from django.contrib.auth.models import User


@pytest.mark.django_db
def test_broadcast_player_change_sends_html_and_json():
    """broadcast_player_change reproduces the bot-checkbox HTML and bot-setting JSON."""
    user = User.objects.create_user(username="testuser")
    player = Player.objects.create(user=user, allow_bot_to_play_for_me=True)

    with patch("app.models.player.send_event") as mock_send_event:
        app.broadcast.broadcast_player_change(player=player, changed=["allow_bot_to_play_for_me"])

        # Two events: HTML for web, JSON for bots.
        assert mock_send_event.call_count == 2

        html_call = mock_send_event.call_args_list[0]
        assert html_call.kwargs["channel"] == f"player:bot-checkbox:{player.pk}"
        assert html_call.kwargs["event_type"] == SSEEventTypes.BOT_CHECKBOX
        assert "bot-plays-for-me-div" in html_call.kwargs["data"]  # HTML content

        json_call = mock_send_event.call_args_list[1]
        assert json_call.kwargs["channel"] == f"player:json:{player.pk}"
        assert json_call.kwargs["event_type"] == SSEEventTypes.BOT_SETTING
        assert json_call.kwargs["data"] == {"allow_bot_to_play_for_me": True}


@pytest.mark.django_db
def test_broadcast_player_change_ignores_unrelated_changes():
    """A change touching neither allow_bot nor current_hand broadcasts nothing.

    In production the app_player trigger (0104) would not even fire for such a
    change; this guards the broadcaster itself as well.
    """
    user = User.objects.create_user(username="testuser")
    player = Player.objects.create(user=user, allow_bot_to_play_for_me=False)

    with patch("app.models.player.send_event") as mock_send_event:
        app.broadcast.broadcast_player_change(player=player, changed=["last_action"])
        assert mock_send_event.call_count == 0


@pytest.mark.django_db
def test_player_save_no_longer_broadcasts():
    """Broadcasting moved to the notifier (see docs/README.listen-notify.md);
    Player.save itself is silent now."""
    user = User.objects.create_user(username="testuser")
    player = Player.objects.create(user=user, allow_bot_to_play_for_me=False)

    with patch("app.models.player.send_event") as mock_send_event:
        player.allow_bot_to_play_for_me = True
        player.save()
        assert mock_send_event.call_count == 0
