"""Test for race condition between bot toggle and player save during calls/plays.

This test verifies that when a player object is saved during a call or play
(to update last_action), it doesn't overwrite the allow_bot_to_play_for_me
field that was toggled by the user.
"""

import pytest

import bridge.card
import bridge.contract
from app.models import Hand, Player
from bridge.contract import Call as libCall


@pytest.mark.django_db()
def test_bot_toggle_not_overwritten_by_call(usual_setup):
    """Test that toggling bot off isn't overwritten when bot makes a call."""
    # Get a hand that's in auction phase - use prepop() to cache players on hand
    # This simulates how the bot loads hands in production
    hand = Hand.objects.prepop().filter(is_complete=False).first()
    assert hand is not None

    # Get the player whose turn it is - must be non-synthetic
    player = hand.player_who_may_call
    assert player is not None

    # If the current player is synthetic, we need to find a non-synthetic player in the hand
    if player.synthetic:
        # Get all non-synthetic players in this hand
        for direction in ["North", "South", "East", "West"]:
            p = getattr(hand, direction)
            if not p.synthetic:
                player = p
                # Make calls until it's this player's turn
                while hand.player_who_may_call != player:
                    hand.add_call(call=libCall.deserialize("Pass"))
                break

    assert not player.synthetic, "Could not find a non-synthetic player"

    # Enable bot play
    player.allow_bot_to_play_for_me = True
    player.save()
    player.refresh_from_db()
    assert player.allow_bot_to_play_for_me is True

    # IMPORTANT: Reload the hand to get fresh cached players
    # This simulates the bot loading a hand at the start of its loop iteration
    hand = Hand.objects.prepop().get(pk=hand.pk)

    # Simulate the race condition:
    # 1. Bot has already loaded the player object (with allow_bot=True)
    # This player is cached on the hand object from the prepop() fetch

    # 2. User toggles bot off in a separate process/transaction
    # We simulate this by using update() which doesn't touch in-memory objects
    Player.objects.filter(pk=player.pk).update(allow_bot_to_play_for_me=False)

    # Verify the database was updated
    player.refresh_from_db()
    assert player.allow_bot_to_play_for_me is False, "Database should have allow_bot=False"

    # But the cached player on the hand still has the old value!
    cached_player = hand.player_who_may_call
    assert cached_player.allow_bot_to_play_for_me is True, (
        "Cached player should still have allow_bot=True (stale)"
    )

    # 3. Bot makes a call using the hand with stale cached player
    # Inside add_call(), it will get the stale cached player and save it
    hand.add_call(call=libCall.deserialize("Pass"))

    # 4. Verify the toggle wasn't overwritten
    player.refresh_from_db()
    assert player.allow_bot_to_play_for_me is False, (
        "Bot toggle was overwritten when player.save() was called during add_call!"
    )


@pytest.mark.django_db()
def test_bot_toggle_not_overwritten_by_play(usual_setup):
    """Test that toggling bot off isn't overwritten when bot plays a card."""
    # Get a hand and progress it to the play phase - use prepop() to cache players
    # This simulates how the bot loads hands in production
    hand = Hand.objects.prepop().filter(is_complete=False).first()
    assert hand is not None

    # Set auction to 1 Club and get to play phase
    from app.test_api import set_auction_to

    set_auction_to(bridge.contract.Bid(level=1, denomination=bridge.card.Suit.CLUBS), hand)

    assert hand.next_seat_to_play is not None

    # Get the player whose turn it is
    player = hand.player_who_controls_seat(hand.next_seat_to_play, right_this_second=True)
    assert player is not None

    # If player is synthetic, play cards until we get to a non-synthetic player
    if player.synthetic:
        for _ in range(4):  # Try up to 4 cards (one trick)
            if player.synthetic:
                card = player.dealt_cards()[0]
                hand.add_play_from_model_player(player=player, card=card)
                if hand.next_seat_to_play:
                    player = hand.player_who_controls_seat(
                        hand.next_seat_to_play, right_this_second=True
                    )
                else:
                    break
            else:
                break

    assert not player.synthetic, "Could not find a non-synthetic player"
    assert hand.next_seat_to_play is not None, "Hand is complete"

    # Enable bot play
    player.allow_bot_to_play_for_me = True
    player.save()
    player.refresh_from_db()
    assert player.allow_bot_to_play_for_me is True

    # IMPORTANT: Reload the hand to get fresh cached players
    # This simulates the bot loading a hand at the start of its loop iteration
    hand = Hand.objects.prepop().get(pk=hand.pk)

    # Simulate the race condition:
    # 1. Bot has already loaded the player object (with allow_bot=True)
    # This player is cached on the hand object from the prepop() fetch

    # 2. User toggles bot off in a separate process/transaction
    # We simulate this by using update() which doesn't touch in-memory objects
    Player.objects.filter(pk=player.pk).update(allow_bot_to_play_for_me=False)

    # Verify the database was updated
    player.refresh_from_db()
    assert player.allow_bot_to_play_for_me is False, "Database should have allow_bot=False"

    # But the cached player on the hand still has the old value!
    cached_player = hand.player_who_controls_seat(hand.next_seat_to_play, right_this_second=True)
    assert cached_player.allow_bot_to_play_for_me is True, (
        "Cached player should still have allow_bot=True (stale)"
    )

    # 3. Bot plays a card using the hand with stale cached player
    card = cached_player.dealt_cards()[0]
    hand.add_play_from_model_player(player=cached_player, card=card)

    # 4. Verify the toggle wasn't overwritten
    player.refresh_from_db()
    assert player.allow_bot_to_play_for_me is False, (
        "Bot toggle was overwritten when player.save() was called during add_play_from_model_player!"
    )
