import collections
import collections.abc
import dataclasses
from typing import Any

ID = Any


@dataclasses.dataclass
class Hand:
    ns_id: ID
    ew_id: ID
    ns_raw_score: int
    ew_raw_score: int
    board_id: ID

    def __post_init__(self) -> None:
        assert any(s == 0 for s in (self.ns_raw_score, self.ew_raw_score)), (
            "At least one score must be zero"
        )


# The three artificial scores of Law 12: average minus for a contestant directly at
# fault, average for one only partly at fault, average plus for one in no way at fault.
# The law states them as bounds -- "at most 40%", "at least 60%" -- and we award exactly
# the bound.
AT_FAULT = 0.4
PARTLY_AT_FAULT = 0.5
NOT_AT_FAULT = 0.6


@dataclasses.dataclass
class AdjustedHand:
    """A board a pair was due to play, from which no result can be obtained.

    Each side gets a fraction of the matchpoints available on that board rather than a
    raw score to be compared with the field.  That is what makes the award knowable
    straight away: 60% of a board is 60% whether or not the rest of the tournament has
    finished.
    """

    ns_id: ID
    ew_id: ID
    board_id: ID
    ns_fraction: float = PARTLY_AT_FAULT
    ew_fraction: float = PARTLY_AT_FAULT


@dataclasses.dataclass
class Scorer:
    hands: collections.abc.Collection[Hand]
    adjustments: collections.abc.Collection[AdjustedHand] = ()

    @staticmethod
    def from_one_raw_score_dict(subject_id: ID, raw_scores_by_id: dict[ID, int]) -> int:
        my_score = raw_scores_by_id[subject_id]
        other_scores = [score for id_, score in raw_scores_by_id.items() if id_ != subject_id]

        matchpoints = 0

        for o in other_scores:
            if my_score == o:
                matchpoints += 1
            elif my_score > o:
                matchpoints += 2

        return matchpoints

    def from_one_board(self, *, hands: collections.abc.Collection[Hand]) -> dict[ID, int]:
        ns_raw_scores_by_id = {}
        ew_raw_scores_by_id = {}

        for h in hands:
            ns_raw_scores_by_id[h.ns_id] = h.ns_raw_score or -h.ew_raw_score
            ew_raw_scores_by_id[h.ew_id] = h.ew_raw_score or -h.ns_raw_score

        ns_matchpoints_by_id = {
            id_: self.from_one_raw_score_dict(id_, ns_raw_scores_by_id)
            for id_ in ns_raw_scores_by_id.keys()
        }
        ew_matchpoints_by_id = {
            id_: self.from_one_raw_score_dict(id_, ew_raw_scores_by_id)
            for id_ in ew_raw_scores_by_id.keys()
        }

        return ns_matchpoints_by_id | ew_matchpoints_by_id

    def matchpoints_by_pairs(self) -> dict[ID, tuple[float, float]]:
        """Each pair's matchpoints, and what percentage of their own maximum that is.

        A pair's percentage is measured against the matchpoints available on the boards
        *they* were down to play, not against the tournament's grand total.  With the
        grand total, a pair who missed a board through no fault of their own paid for it
        twice: no matchpoints from the board, and a divisor that counted it anyway.

        The matchpoints available on a board are 2 * (results - 1), counting only the
        tables that actually produced a result: those are the tables a result gets
        compared against.  An adjusted score is a fraction of that same maximum.
        """
        played_by_board: dict[ID, list[Hand]] = collections.defaultdict(list)
        for h in self.hands:
            played_by_board[h.board_id].append(h)

        adjusted_by_board: dict[ID, list[AdjustedHand]] = collections.defaultdict(list)
        for a in self.adjustments:
            adjusted_by_board[a.board_id].append(a)

        earned: dict[ID, float] = collections.defaultdict(float)
        possible: dict[ID, float] = collections.defaultdict(float)

        for board_id in set(played_by_board) | set(adjusted_by_board):
            hands = played_by_board[board_id]
            available = float(2 * (len(hands) - 1)) if hands else 0.0

            for pair, mps in self.from_one_board(hands=hands).items():
                earned[pair] += mps
                possible[pair] += available

            for adjustment in adjusted_by_board[board_id]:
                for pair, fraction in (
                    (adjustment.ns_id, adjustment.ns_fraction),
                    (adjustment.ew_id, adjustment.ew_fraction),
                ):
                    earned[pair] += fraction * available
                    possible[pair] += available

        return {
            pair: (
                mps,
                float("nan") if possible[pair] == 0 else 100 * mps / possible[pair],
            )
            for pair, mps in earned.items()
        }
