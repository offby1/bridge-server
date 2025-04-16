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


@dataclasses.dataclass
class Scorer:
    hands: collections.abc.Collection[Hand]

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

    def matchpoints_by_pairs(self) -> dict[ID, tuple[int, float]]:
        by_board = collections.defaultdict(list)

        for h in self.hands:
            by_board[h.board_id].append(h)

        total_available = 2 * sum(len(hands) - 1 for hands in by_board.values())

        mps_by_pair = {}

        for b, hands in by_board.items():
            for pair, mps in self.from_one_board(hands=hands).items():
                if pair not in mps_by_pair:
                    mps_by_pair[pair] = [0, 0.0]

                mps_by_pair[pair][0] += mps
                mps_by_pair[pair][1] += (
                    float("nan") if total_available == 0 else 100 * mps / total_available
                )

        return {k: (int(v[0]), float(v[1])) for k, v in mps_by_pair.items()}
