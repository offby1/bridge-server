import logging

import pytest
from django.contrib.auth.models import AnonymousUser

import app.visibility
from app.models import Hand, Player, Tournament
from app.testutils import create_a_tournament, play_out_hand
from app.visibility import BoardRelationship, HandViewMode

logger = logging.getLogger()


@pytest.fixture
def setup(db: None) -> Tournament:
    t = create_a_tournament(stage="playing", boards_per_round_per_table=1)

    # play board 1 fully
    b1_hands = Hand.objects.filter(board__display_number=1)
    assert b1_hands.count() == 2
    for h in b1_hands:
        play_out_hand(h)
    # play only one hand of board 2
    b2_hands = Hand.objects.filter(board__display_number=2)
    assert b2_hands.count() == 2
    b2_hands_first = b2_hands.first()
    assert b2_hands_first is not None
    play_out_hand(b2_hands_first)

    assert Hand.objects.count() == 4

    return t


def test_alt(setup: Tournament) -> None:
    import pprint

    pprint.pprint(setup.get_movement())

    all_users = [p.user for p in Player.objects.all()] + [AnonymousUser]

    def expect(expected: HandViewMode, *, hand: Hand, user) -> None:
        __tracebackhide__ = True
        viewer = getattr(user, "player", None)
        actual = app.visibility.hand_access(hand=hand, viewer=viewer).mode
        if actual is not expected:
            pytest.fail(f"{user}: expected {expected} but got {actual}")

    # Board 1 has been fully played, so everybody -- anonymous included -- gets the
    # review page.
    for h in Hand.objects.filter(board__display_number=1):
        for u in all_users:
            expect(HandViewMode.read_only, hand=h, user=u)

    for h in Hand.objects.filter(board__display_number=2):
        # Board 2 has been only partially played.
        for u in all_users:
            if u.is_anonymous:
                expect(HandViewMode.forbidden, hand=h, user=u)
                continue

            relationship, at_hand = app.visibility.board_relationship(
                board=h.board, viewer=u.player
            )
            match relationship:
                case BoardRelationship.already_played_it:
                    expect(HandViewMode.read_only, hand=h, user=u)
                case BoardRelationship.currently_playing_it:
                    expect(
                        HandViewMode.interactive if h == at_hand else HandViewMode.forbidden,
                        hand=h,
                        user=u,
                    )
                case BoardRelationship.never_seen_it:
                    expect(HandViewMode.forbidden, hand=h, user=u)


def test_a_refusal_explains_itself(setup: Tournament) -> None:
    """Every `forbidden` carries text for the 403 body; nothing else does."""
    hand = Hand.objects.filter(board__display_number=2, is_complete=False).first()
    assert hand is not None

    stranger = Player.objects.create_synthetic()

    refused = app.visibility.hand_access(hand=hand, viewer=stranger)
    assert refused.mode is HandViewMode.forbidden
    assert "never seen board" in refused.explanation

    anonymous = app.visibility.hand_access(hand=hand, viewer=None)
    assert anonymous.mode is HandViewMode.forbidden
    assert "Anonymous" in anonymous.explanation

    allowed = app.visibility.hand_access(hand=hand, viewer=hand.North)
    assert allowed.mode is not HandViewMode.forbidden
    assert allowed.explanation == ""


def test_an_abandoned_hand_is_read_only_for_the_players_who_left_it(setup: Tournament) -> None:
    """There is nothing left to play, so the interactive page has nothing to offer."""
    hand = Hand.objects.filter(board__display_number=2, is_complete=False).first()
    assert hand is not None
    north = hand.North

    assert app.visibility.hand_access(hand=hand, viewer=north).mode is HandViewMode.interactive

    hand.abandoned_because = "somebody wandered off"
    hand.save()

    assert app.visibility.hand_access(hand=hand, viewer=north).mode is HandViewMode.read_only
