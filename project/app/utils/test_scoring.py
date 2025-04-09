from .scoring import Hand, Scorer


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
    assert scorer.matchpoints_by_pairs() == {
        1: 5,
        2: 8,
        3: 12,
        4: 5,
        5: 10,
        6: 0,
        7: 2,
        8: 7,
        13: 4,
        11: 0,
        9: 7,
        14: 2,
        12: 12,
        10: 10,
    }
