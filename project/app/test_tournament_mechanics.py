"""
These tests are likely redundant with many exsiting ones, but I'm sort of starting over.

when a tournament signup deadline expires (i.e., when we first know exactly who the players are):
- we create all the boards, grouped by round number

when a tournament round starts:
- (ensure boards for this round exist)
- (ensure no incomplete hands exist)
- we create one hand per table, using the boards for that round

when any of those hands ends:
- *if all the other hands in the round have also ended*: [1]
  - if the tournament is over:
    - eject all pairs
    - send suitable SSE event
  - otherwise ("test_last_hand_in_a_round"):
    - start a new tournament round (item #1 above)
- otherwise:
  - if there are unplayed boards for this table & round ("test_first_hand_to_end_in_a_round"):
    - we create another hand at that same table, using the next board for this table & round (i.e., the next board in that group)
  - otherwise ("test_last_hand_in_a_group"):
    - do nothing for this table

[1] I went back and forth between "create a new hand (in the next round) at table T as soon as the last hand at table T completes", and "wait until all hands of that round have completed and then create a new hand (in the next round) for each table".  I'm settling on the latter because the former would require that I somehow ensure that the new hand's players -- half of whom come from another table -- are done with *their* hand, and that sounds messy.
"""

import collections

import pytest

from app.models import Hand, Tournament

from .testutils import create_a_tournament, play_out_hand, play_out_round


@pytest.fixture
def small_tournament_during_play(db) -> Tournament:
    return create_a_tournament(stage="playing", boards_per_round_per_table=2)


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
    mvmt = small_tournament_during_play.get_movement()
    assert mvmt.boards_per_round_per_table == 2

    num_hands_before = small_tournament_during_play.hands().count()
    assert num_hands_before == 2

    h = small_tournament_during_play.hands().filter(table_display_number=1).first()
    assert h is not None
    assert not h.is_complete

    play_out_hand(h)

    # One original hand for each table, plus a new board at table 1
    assert small_tournament_during_play.hands().count() == 3


def test_last_hand_to_end_in_a_round(small_tournament_during_play: Tournament) -> None:
    mvmt = small_tournament_during_play.get_movement()

    assert mvmt.boards_per_round_per_table == 2

    def summarize(h: Hand):
        return (h.table_display_number, h.board.display_number)

    assert set([summarize(h) for h in small_tournament_during_play.hands()]) == {(1, 1), (2, 1)}

    for h in small_tournament_during_play.hands().filter(is_complete=False):
        play_out_hand(h)

    assert set(
        [summarize(h) for h in small_tournament_during_play.hands().filter(is_complete=True)]
    ) == {
        (1, 1),
        (2, 1),
    }

    assert set(
        [summarize(h) for h in small_tournament_during_play.hands().filter(is_complete=False)]
    ) == {
        (1, 2),
        (2, 2),
    }

    for h in small_tournament_during_play.hands().filter(is_complete=True):
        assert h.abandoned_because is None


def test_last_hand_in_a_round(small_tournament_during_play: Tournament) -> None:
    play_out_round(small_tournament_during_play)

    assert small_tournament_during_play.rounds_played() == (1, 0)

    hands_by_round = collections.defaultdict(list)
    for h in Hand.objects.all():
        hands_by_round[h.board.group].append(h)

    assert len(hands_by_round["A"]) == 4
    assert len(hands_by_round["B"]) == 2


def test_tournament_is_over(small_tournament_during_play: Tournament) -> None:
    assert not small_tournament_during_play.is_complete

    play_out_round(small_tournament_during_play)
    assert not small_tournament_during_play.is_complete

    play_out_round(small_tournament_during_play)
    assert small_tournament_during_play.is_complete

    assert small_tournament_during_play.rounds_played() == (2, 0)
