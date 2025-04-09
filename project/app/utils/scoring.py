import collections
import collections.abc
import dataclasses


ID = collections.abc.Hashable


@dataclasses.dataclass
class Hand:
    ns_id: ID
    ew_id: ID
    ns_raw_score: int
    ew_raw_score: int
    board_id: ID

    def __post_init__(self) -> None:
        assert any(
            s == 0 for s in (self.ns_raw_score, self.ew_raw_score)
        ), "At least one score must be zero"


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

        print(f"{subject_id=} {my_score=} {other_scores=} => {matchpoints=}")

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

        import pprint

        pprint.pprint(("ns", ns_matchpoints_by_id))
        pprint.pprint(("ew", ew_matchpoints_by_id))
        rv = ns_matchpoints_by_id | ew_matchpoints_by_id
        pprint.pprint(("rv", rv))
        return rv

    def matchpoints_by_pairs(self) -> dict[ID, int]:
        by_board = collections.defaultdict(list)

        for h in self.hands:
            by_board[h.board_id].append(h)

        mps_by_pair: dict[ID, int] = collections.defaultdict(int)

        for b, hands in by_board.items():
            print(f"Computing matchpoints for board {b}")
            for pair, mps in self.from_one_board(hands=hands).items():
                mps_by_pair[pair] += mps

        return mps_by_pair
