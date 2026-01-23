from unittest.mock import patch

import pytest
from app.models import Player
from django.contrib.auth.models import User


@pytest.mark.django_db
def test_bot_toggle_broadcasts_sse_event():
    """Test that changing allow_bot_to_play_for_me sends SSE update."""
    user = User.objects.create_user(username="testuser")
    player = Player.objects.create(user=user, allow_bot_to_play_for_me=False)

    with patch("app.models.player.send_event") as mock_send_event:
        # Toggle the bot flag
        player.allow_bot_to_play_for_me = True
        player.save()

        # Should have sent two events: HTML for web, JSON for bots
        assert mock_send_event.call_count == 2

        # Check HTML event
        html_call = mock_send_event.call_args_list[0]
        assert html_call.kwargs["channel"] == f"player:bot-checkbox:{player.pk}"
        assert html_call.kwargs["event_type"] == "message"
        assert "bot-plays-for-me-div" in html_call.kwargs["data"]  # HTML content

        # Check JSON event
        json_call = mock_send_event.call_args_list[1]
        assert json_call.kwargs["channel"] == f"player:json:{player.pk}"
        assert json_call.kwargs["event_type"] == "message"
        assert json_call.kwargs["data"] == {"allow_bot_to_play_for_me": True}


@pytest.mark.django_db
def test_no_broadcast_when_field_unchanged():
    """Test that save without changes doesn't broadcast."""
    user = User.objects.create_user(username="testuser")
    player = Player.objects.create(user=user, allow_bot_to_play_for_me=False)

    with patch("app.models.player.send_event") as mock_send_event:
        # Save without changing anything
        player.save()

        # Should not have sent any events
        assert mock_send_event.call_count == 0


@pytest.mark.django_db
def test_no_broadcast_on_create():
    """Test that creating a new player doesn't broadcast."""
    with patch("app.models.player.send_event") as mock_send_event:
        user = User.objects.create_user(username="testuser")
        Player.objects.create(user=user, allow_bot_to_play_for_me=False)

        # Should not broadcast on initial create
        assert mock_send_event.call_count == 0
