from unittest.mock import patch

import pytest

import bridge.card
import bridge.contract
from app.models import Hand


@pytest.mark.django_db
def test_dummy_checkbox_updates_when_contract_determined(usual_setup: Hand) -> None:
    """Test that dummy's checkbox gets SSE update when they become dummy."""
    hand: Hand = usual_setup

    # Get the players

    # Clear any existing calls
    hand.call_set.all().delete()

    with patch("app.models.hand.send_event") as mock_send_event:
        # Auction: North opens 1C, everyone passes
        hand.add_call(
            call=bridge.contract.Bid(level=1, denomination=bridge.card.Suit.CLUBS)
        )  # North
        hand.add_call(call=bridge.contract.Pass)  # East
        hand.add_call(call=bridge.contract.Pass)  # South

        # Before this pass, contract is not determined
        assert not hand.auction.found_contract

        # This pass determines the contract (3 passes in a row after a bid)
        hand.add_call(call=bridge.contract.Pass)  # West

        # Now contract should be determined
        assert hand.auction.found_contract

        # Check that dummy received an SSE update
        # Find calls to send_event with the dummy's bot-checkbox channel
        dummy = hand.model_dummy
        assert dummy is not None, "Should have a dummy after contract is determined"

        # Look for the call that sent to dummy's bot-checkbox channel
        dummy_updates = [
            call
            for call in mock_send_event.call_args_list
            if call.kwargs.get("channel") == f"player:bot-checkbox:{dummy.pk}"
        ]

        assert len(dummy_updates) >= 1, f"Dummy {dummy.name} should receive checkbox update"

        # Verify the HTML contains disabled attribute
        html_call = dummy_updates[0]
        assert html_call.kwargs["event_type"] == "message"
        html_content = html_call.kwargs["data"]
        assert "disabled" in html_content, "Checkbox should be disabled for dummy"
        assert "dummy" in html_content.lower(), "Should indicate this is dummy"


@pytest.mark.django_db
def test_declarer_toggle_updates_dummy_checkbox(usual_setup: Hand) -> None:
    """Test that when declarer toggles, dummy's checkbox also updates."""
    hand: Hand = usual_setup

    # Clear existing calls and set up a contract
    hand.call_set.all().delete()

    # Create contract: North opens 1C, everyone passes
    hand.add_call(call=bridge.contract.Bid(level=1, denomination=bridge.card.Suit.CLUBS))
    hand.add_call(call=bridge.contract.Pass)
    hand.add_call(call=bridge.contract.Pass)
    hand.add_call(call=bridge.contract.Pass)

    # Now we have a contract - North is declarer, South is dummy
    assert hand.auction.found_contract
    declarer = hand.model_declarer
    dummy = hand.model_dummy
    assert declarer is not None
    assert dummy is not None
    assert declarer != dummy

    with patch("app.models.player.send_event") as mock_send_event:
        # Declarer toggles their bot checkbox
        # Note: If declarer is synthetic, they must have allow_bot=True, so we can only toggle True->False for non-synthetic
        if declarer.synthetic:
            pytest.skip("Declarer is synthetic and must have allow_bot_to_play_for_me=True")

        original_value = declarer.allow_bot_to_play_for_me
        declarer.allow_bot_to_play_for_me = not original_value
        declarer.save()

        # Should broadcast to both declarer and dummy
        channels_updated = {call.kwargs.get("channel") for call in mock_send_event.call_args_list}

        assert f"player:bot-checkbox:{declarer.pk}" in channels_updated, (
            "Declarer's checkbox should update"
        )
        assert f"player:bot-checkbox:{dummy.pk}" in channels_updated, (
            "Dummy's checkbox should also update"
        )
