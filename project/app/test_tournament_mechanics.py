"""
These tests are likely redundant with many exsiting ones, but I'm sort of starting over.

They are meant to reflect my thoughts from ../../../when-do-hands-and-boards-get-created
"""

import collections
import datetime
from typing import Generator

from freezegun import freeze_time
import pytest

from app.models import Hand, Player, Tournament
from app.models.tournament import _do_signup_expired_stuff

from .testutils import play_out_hand


SIGNUP_DEADLINE = datetime.datetime.fromisoformat("2000-01-01T00:00:00Z")
PLAY_COMPLETION_DEADLINE = SIGNUP_DEADLINE + datetime.timedelta(seconds=3600)


@pytest.fixture
def small_tournament_at_signup_deadline(db) -> Generator[Tournament]:
    with freeze_time(SIGNUP_DEADLINE):
        # set signup deadline to be more or less "now"
        t: Tournament
        t, _ = Tournament.objects.get_or_create_tournament_open_for_signups(
            play_completion_deadline=PLAY_COMPLETION_DEADLINE
        )

        # Create 8 players
        for _ in range(4):
            p1 = Player.objects.create_synthetic()
            p2 = Player.objects.create_synthetic()
            p1.partner_with(p2)

        # Sign 'em all up
        for p in Player.objects.all():
            t.sign_up_player_and_partner(p)

        yield t


@pytest.fixture
def small_tournament_during_play(small_tournament_at_signup_deadline) -> Generator[Tournament]:
    with freeze_time(SIGNUP_DEADLINE + (PLAY_COMPLETION_DEADLINE - SIGNUP_DEADLINE) // 2):
        _do_signup_expired_stuff(small_tournament_at_signup_deadline)

        yield small_tournament_at_signup_deadline


def test_start_of_round_creates_one_hand_per_table(
    small_tournament_during_play: Tournament,
) -> None:
    hands_per_table: dict[int, list[Hand]] = collections.defaultdict(list)
    h: Hand

    for h in small_tournament_during_play.hands():
        assert h.table_display_number is not None
        hands_per_table[h.table_display_number].append(h)

    assert len(hands_per_table) == 2

    for table, hands in hands_per_table.items():
        assert len(hands) == 1

        hand = hands[0]
        assert hand.board.group == "A"  # first round, first letter.


def test_first_hand_to_end_in_a_round(small_tournament_during_play: Tournament) -> None:
    num_hands_before = small_tournament_during_play.hands().count()
    h = small_tournament_during_play.hands().first()
    assert h is not None
    play_out_hand(h)

    mvmt = small_tournament_during_play.get_movement()
    assert mvmt.boards_per_round_per_table > 1

    num_hands_after = small_tournament_during_play.hands().count()
    assert num_hands_after == num_hands_before + 1
