"""
Test that anonymous users can view hands from completed tournaments.

This test reproduces a bug where anonymous users are blocked from viewing
hands in completed tournaments, even though they should have read-only access
to all hands once a tournament is complete.
"""

import datetime

import freezegun
import pytest
from django.contrib.auth.models import AnonymousUser

from app.models import Hand, Player, Tournament
from app.models.tournament import check_for_expirations
from app.views.hand import _error_response_or_viewfunc, _everything_read_only_view


@pytest.fixture
def completed_tournament_with_abandoned_hand(nearly_completed_tournament: Tournament) -> Hand:
    """
    Create a completed tournament where at least one hand was abandoned due to deadline.

    The tournament is marked as complete because the play completion deadline passed,
    but some hands were never finished and are marked as abandoned.
    """
    # Get an incomplete hand before we expire the tournament
    incomplete_hand = Hand.objects.filter(is_complete=False).first()
    assert incomplete_hand is not None, "Should have at least one incomplete hand"

    # Set a play completion deadline and let it pass
    datetime.datetime.fromisoformat("2025-09-28T16:00:00+00:00")
    deadline = datetime.datetime.fromisoformat("2025-09-28T16:13:51.704288+00:00")

    nearly_completed_tournament.play_completion_deadline = deadline
    nearly_completed_tournament.save()

    # Fast forward past the deadline and check for expirations
    # This will mark incomplete hands as abandoned and mark the tournament as complete
    with freezegun.freeze_time(deadline + datetime.timedelta(hours=1)):
        check_for_expirations(__name__)

    # Reload the tournament and hand
    nearly_completed_tournament.refresh_from_db()
    incomplete_hand.refresh_from_db()

    # Verify the tournament is complete and the hand is abandoned
    assert nearly_completed_tournament.is_complete, "Tournament should be complete"
    assert incomplete_hand.is_abandoned, "Hand should be abandoned"

    return incomplete_hand


def test_anonymous_user_can_view_hand_from_completed_tournament(
    completed_tournament_with_abandoned_hand: Hand,
) -> None:
    """
    Test that anonymous users can view hands from completed tournaments.

    When a tournament is complete, all hands (including abandoned ones) should be
    viewable by everyone, including anonymous users. This is the expected behavior
    for completed tournaments where results are public.

    BUG: Currently fails because anonymous users get HttpResponseForbidden even
    when the tournament is complete.
    """
    hand = completed_tournament_with_abandoned_hand
    anonymous_user = AnonymousUser()

    # Verify prerequisites
    assert hand.tournament.is_complete, "Tournament must be complete for this test"
    assert hand.is_abandoned, "Hand must be abandoned for this test"

    # Anonymous users should be able to view hands from completed tournaments
    result = _error_response_or_viewfunc(hand, anonymous_user)

    assert result == _everything_read_only_view, (
        f"Anonymous users should be able to view hands from completed tournaments, "
        f"but got {result} instead of _everything_read_only_view"
    )


def test_authenticated_non_participant_can_view_hand_from_completed_tournament(
    completed_tournament_with_abandoned_hand: Hand,
) -> None:
    """
    Test that authenticated users who didn't participate can view completed tournaments.

    This tests a related scenario: a logged-in user (like "bob") who wasn't part of
    the tournament should also be able to view abandoned hands once the tournament
    is complete.
    """
    hand = completed_tournament_with_abandoned_hand

    # Create a player who wasn't part of this tournament
    non_participant = Player.objects.create_synthetic()
    user = non_participant.user

    # Verify prerequisites
    assert hand.tournament.is_complete, "Tournament must be complete for this test"
    assert hand.is_abandoned, "Hand must be abandoned for this test"
    assert non_participant not in [hand.North, hand.South, hand.East, hand.West], (
        "Test player should not be a participant in this hand"
    )

    # Non-participants should be able to view hands from completed tournaments
    result = _error_response_or_viewfunc(hand, user)

    assert result == _everything_read_only_view, (
        f"Non-participants should be able to view hands from completed tournaments, "
        f"but got {result} instead of _everything_read_only_view"
    )
