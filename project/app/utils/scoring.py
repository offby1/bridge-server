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
AVERAGE = 0.5
AT_FAULT = 0.4
PARTLY_AT_FAULT = AVERAGE
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

    def _fractions_from_one_board(
        self,
        *,
        played: collections.abc.Collection[Hand],
        adjusted: collections.abc.Collection[AdjustedHand],
    ) -> collections.abc.Iterator[tuple[ID, float]]:
        """How each pair did on one board, as a fraction of what was going on it.

        Three cases, and the middle one is the point of this method.  Two or more
        results get matchpointed against each other as usual.  A lone result has nothing
        to be compared with, so it earns average: however well they actually played, the
        board says nothing about it, and pretending otherwise would be inventing
        information.  No results at all leaves only the adjusted scores.
        """
        if len(played) > 1:
            available = 2 * (len(played) - 1)
            for pair, mps in self.from_one_board(hands=played).items():
                yield pair, mps / available
        elif len(played) == 1:
            lonely = next(iter(played))
            yield lonely.ns_id, AVERAGE
            yield lonely.ew_id, AVERAGE

        for adjustment in adjusted:
            yield adjustment.ns_id, adjustment.ns_fraction
            yield adjustment.ew_id, adjustment.ew_fraction

    def matchpoints_by_pairs(self) -> dict[ID, tuple[float, float]]:
        """Each pair's matchpoints, and what percentage of their own boards that is.

        Scoring works in fractions of a board and averages them, so that every board a
        pair were down to play counts the same whether four tables played it or one.
        Totting up raw matchpoints and dividing by a grand total does not do that: it
        weights each board by how big its field happened to be, and it collapses
        entirely in a two-table event where one table walks out, since every board is
        then left with a single result and nothing to compare it against.  Everybody
        scored 0 out of 0.

        The matchpoints we report alongside are the fraction times what the board was
        worth -- 2 * (pairs who were down to play it - 1).  For a tournament where
        everyone played everything, which is the ordinary case, that is exactly the
        matchpoint count you'd get by hand.
        """
        played_by_board: dict[ID, list[Hand]] = collections.defaultdict(list)
        for h in self.hands:
            played_by_board[h.board_id].append(h)

        adjusted_by_board: dict[ID, list[AdjustedHand]] = collections.defaultdict(list)
        for a in self.adjustments:
            adjusted_by_board[a.board_id].append(a)

        earned: dict[ID, float] = collections.defaultdict(float)
        fractions: dict[ID, list[float]] = collections.defaultdict(list)

        for board_id in set(played_by_board) | set(adjusted_by_board):
            played = played_by_board[board_id]
            adjusted = adjusted_by_board[board_id]

            top = float(2 * (len(played) + len(adjusted) - 1))

            for pair, fraction in self._fractions_from_one_board(played=played, adjusted=adjusted):
                fractions[pair].append(fraction)
                earned[pair] += fraction * top

        return {
            pair: (earned[pair], 100 * sum(theirs) / len(theirs))
            for pair, theirs in fractions.items()
        }
