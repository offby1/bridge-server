import math
from collections.abc import Hashable

from .scoring import AT_FAULT, NOT_AT_FAULT, PARTLY_AT_FAULT, AdjustedHand, Hand, Scorer


def test_base_case() -> None:
    scorer = Scorer(hands=[])
    assert scorer.matchpoints_by_pairs() == {}


# https://www.acbl.org/learn/#scoring then click the "Matchpoints" icon
def test_from_ACBL_example() -> None:
    hands = [
        Hand(ns_id=1, ew_id=8, ns_raw_score=420, ew_raw_score=0, board_id=1),
        Hand(ns_id=2, ew_id=13, ns_raw_score=430, ew_raw_score=0, board_id=1),
        Hand(ns_id=3, ew_id=11, ns_raw_score=500, ew_raw_score=0, board_id=1),
        Hand(ns_id=4, ew_id=9, ns_raw_score=420, ew_raw_score=0, board_id=1),
        Hand(ns_id=5, ew_id=14, ns_raw_score=450, ew_raw_score=0, board_id=1),
        Hand(ns_id=6, ew_id=12, ns_raw_score=0, ew_raw_score=50, board_id=1),
        Hand(ns_id=7, ew_id=10, ns_raw_score=170, ew_raw_score=0, board_id=1),
    ]

    scorer = Scorer(hands=hands)
    approximate_expected: dict[Hashable, tuple[int, float]] = {
        1: (5, 42),
        2: (8, 67),
        3: (12, 100),
        4: (5, 42),
        5: (10, 83),
        6: (0, 0),
        7: (2, 17),
        8: (7, 58),
        13: (4, 33),
        11: (0, 0),
        9: (7, 58),
        14: (2, 17),
        12: (12, 100),
        10: (10, 83),
    }
    for pair_id, (mps, appx_pct) in scorer.matchpoints_by_pairs().items():
        assert mps == approximate_expected[pair_id][0]
        assert round(appx_pct) == approximate_expected[pair_id][1]


def _three_way_board(board_id: int) -> list[Hand]:
    """One board, three tables, N/S scoring 400, 300 and 200 on it."""
    return [
        Hand(
            ns_id="ns_top", ew_id="ew_bottom", ns_raw_score=400, ew_raw_score=0, board_id=board_id
        ),
        Hand(ns_id="ns_mid", ew_id="ew_mid", ns_raw_score=300, ew_raw_score=0, board_id=board_id),
        Hand(
            ns_id="ns_bottom", ew_id="ew_top", ns_raw_score=200, ew_raw_score=0, board_id=board_id
        ),
    ]


def test_a_pair_is_measured_against_their_own_boards_only() -> None:
    """Missing a board must not shrink the percentage of the boards you did play.

    "ns_top" plays the first board only, and tops it, so 100%.  Dividing instead by the
    tournament's grand total -- 4 matchpoints on the three-table board plus 2 on the
    two-table one -- would have given them 4/6, or 67%, for a board they won outright.

    "ns_mid" plays both: middling on the first (2 of 4) and top of the smaller field on
    the second (2 of 2), so 4 of their own 6.
    """
    hands = _three_way_board(1) + [
        h for h in _three_way_board(2) if h.ns_id != "ns_top" and h.ew_id != "ew_bottom"
    ]

    scores = Scorer(hands=hands).matchpoints_by_pairs()

    assert scores["ns_top"] == (4, 100)
    assert scores["ns_mid"][0] == 4
    assert round(scores["ns_mid"][1]) == 67
    assert scores["ns_bottom"] == (0, 0)


def test_an_adjusted_score_is_a_fraction_of_that_board() -> None:
    """Law 12's three awards, as fractions of the matchpoints available on the board."""
    # Three tables have a result; a fourth pairing never played it.
    hands = _three_way_board(1)
    available = 2 * (len(hands) - 1)

    scores = Scorer(
        hands=hands,
        adjustments=[
            AdjustedHand(
                ns_id="ns_quitter",
                ew_id="ew_stranded",
                board_id=1,
                ns_fraction=AT_FAULT,
                ew_fraction=NOT_AT_FAULT,
            )
        ],
    ).matchpoints_by_pairs()

    assert scores["ns_quitter"] == (AT_FAULT * available, 40)
    assert scores["ew_stranded"] == (NOT_AT_FAULT * available, 60)

    # The pairs who did play are scored against each other exactly as before.
    assert scores["ns_mid"] == (2, 50)


def test_an_adjusted_score_does_not_dilute_the_boards_you_played() -> None:
    """A pair awarded 60% on one board and topping another finishes above 60%."""
    hands = _three_way_board(1) + _three_way_board(2)
    available = 2 * 2

    scores = Scorer(
        hands=hands,
        adjustments=[
            AdjustedHand(
                ns_id="ns_top",
                ew_id="ew_bottom",
                board_id=3,
                ns_fraction=NOT_AT_FAULT,
                ew_fraction=NOT_AT_FAULT,
            )
        ],
    ).matchpoints_by_pairs()

    # Two boards topped outright, plus 60% of a board they never got to play.  The board
    # they missed had no result at all, so there were no matchpoints available on it and
    # the award is worth nothing either way -- what matters is that it doesn't drag them
    # below the 100% they earned.
    assert scores["ns_top"] == (2 * available, 100)


def test_both_pairs_partly_at_fault() -> None:
    """Nobody walked out; the clock just ran out on them.  Average for each."""
    hands = _three_way_board(1)
    available = 2 * (len(hands) - 1)

    scores = Scorer(
        hands=hands,
        adjustments=[AdjustedHand(ns_id="ns_slow", ew_id="ew_slow", board_id=1)],
    ).matchpoints_by_pairs()

    for pair in ("ns_slow", "ew_slow"):
        assert scores[pair] == (PARTLY_AT_FAULT * available, 50)


def test_a_board_nobody_finished_is_worth_nothing_to_anybody() -> None:
    """With no result to compare against, there are no matchpoints to apportion."""
    scores = Scorer(
        hands=[],
        adjustments=[AdjustedHand(ns_id="ns", ew_id="ew", board_id=1, ns_fraction=NOT_AT_FAULT)],
    ).matchpoints_by_pairs()

    assert scores["ns"][0] == 0
    assert math.isnan(scores["ns"][1])
