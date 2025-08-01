"""
# can Player P view hand H or H.board?

- if player P *can never* play hand H, they can see everything about both.  (test_running_tournament_irrelevant_players)
  This means: hand H is part of tournament T, and T's signup deadline has passed; *and* P never signed up for T.
- if the tournament T to which H.board belongs is completed, everyone can see everything. (test_completed_tournament)
- if player P has already played hand H *and* H is *completed*, they can see everything about both. (test_player_has_played_board)
- if player P is *currently* playing hand H, they can see only their own cards, and the dummy. (test_player_has_played_board, test_one_card_played)
  Also, maybe: the auction history, and the play history.  In real tournaments, the auction history vanishes once it has settled, and the only play history that is visible is the current trick.
- if player P has already completed a hand H with board B, and wants to look at *incomplete* hand I that *also* includes board B, they can see everything. (test_weirdo_special_case)
"""

import datetime
from typing import Generator

import freezegun
import pytest

from app.models import Board, Hand, Player, Tournament
from app.models.tournament import check_for_expirations
from bridge.card import Suit
from bridge.contract import Bid
from bridge.seat import Seat as libSeat

from .testutils import find_incomplete_hand, play_out_hand, play_out_round, set_auction_to


@pytest.fixture
def completed_tournament(nearly_completed_tournament: Tournament) -> Hand:
    play_out_round(nearly_completed_tournament)

    assert nearly_completed_tournament.is_complete
    rv = nearly_completed_tournament.hands().first()
    assert rv is not None
    return rv


def test_completed_tournament(completed_tournament: Hand) -> None:
    non_tournament_player = Player.objects.create_synthetic()
    assert non_tournament_player is not None

    h = completed_tournament
    some_tournament_player = h.North

    # ok now try various flavors of player
    for player in [None, some_tournament_player, non_tournament_player]:
        for board in h.tournament.board_set.all():
            for direction in libSeat:
                assert board.can_see_cards_at(
                    player=player,
                    direction_letter=direction.value,
                ), f"Uh, {player} can't see {board} at {direction}?!"


def test_running_tournament_irrelevant_players(nearly_completed_tournament: Tournament) -> None:
    hand = find_incomplete_hand(nearly_completed_tournament)
    assert hand is not None

    assert not hand.tournament.is_complete
    assert not hand.is_complete

    non_tournament_player = Player.objects.create_synthetic()

    for player in [None, non_tournament_player]:
        board: Board = hand.board
        for direction in libSeat:
            can_see = board.can_see_cards_at(
                player=player,
                direction_letter=direction.value,
            )
            assert can_see == (player is not None)


def test_running_tournament_relevant_player_not_yet_played_board(
    nearly_completed_tournament: Tournament,
) -> None:
    hand: Hand | None = Hand.objects.first()
    assert hand is not None

    for player in Player.objects.all():
        for board in Board.objects.all():
            hand = player.hand_at_which_we_played_board(board)
            if hand is None:
                for direction in libSeat:
                    assert not board.can_see_cards_at(
                        player=player,
                        direction_letter=direction.value,
                    ), f"Whoa -- {player} can see {board} at {direction}?!"


def test_player_has_played_board(
    nearly_completed_tournament: Tournament,
) -> None:
    for player in Player.objects.all():
        board: Board
        for board in Board.objects.all():
            hand: Hand = player.hand_at_which_we_played_board(board)

            if hand is None:
                continue

            for d_letter, p in hand.players_by_direction_letter.items():
                if p == player:
                    assert board.can_see_cards_at(
                        player=p,
                        direction_letter=d_letter,
                    ), f"Hey now -- {player} can't see their own cards ({board} at {d_letter})?!"

                if hand.is_complete:
                    assert board.can_see_cards_at(
                        player=p,
                        direction_letter=d_letter,
                    ), f"Hey now -- {player} can't see cards at *completed* {board} at {d_letter}?!"


@pytest.fixture
def tournament_starting_now(fresh_tournament: Hand) -> Generator[Hand]:
    Today = datetime.datetime.fromisoformat("2012-01-10T00:00:00Z")
    Tomorrow = Today + datetime.timedelta(seconds=3600 * 24)

    the_tournament: Tournament | None = Tournament.objects.first()
    assert the_tournament is not None
    the_tournament.play_completion_deadline = Tomorrow
    the_tournament.save()

    with freezegun.freeze_time(Today):
        check_for_expirations(__name__)

        hand: Hand | None = Hand.objects.first()
        assert hand is not None

        yield hand


def test_zero_cards_played(tournament_starting_now: Hand) -> None:
    expect_visibility(
        [
            # Everyone can see their own hand, but that's all.
            # n, e, s, w <-- viewers
            [1, 0, 0, 0],  # n seat
            [0, 1, 0, 0],  # e  |
            [0, 0, 1, 0],  # s  |
            [0, 0, 0, 1],  # w  v
        ],
        hand=tournament_starting_now,
    )


def test_one_card_played(tournament_starting_now: Hand) -> None:
    h: Hand = tournament_starting_now
    set_auction_to(Bid(level=1, denomination=Suit.CLUBS), h)

    assert h.player_who_may_play is not None

    libCard = h.get_xscript().slightly_less_dumb_play().card

    h.add_play_from_model_player(player=h.player_who_may_play, card=libCard)

    expect_visibility(
        [
            # Dummy's hand is visible after the opening lead.
            # n, e, s, w <-- viewers
            [1, 0, 0, 0],  # n seat
            [0, 1, 0, 0],  # e  |
            [1, 1, 1, 1],  # s  | (dummy)
            [0, 0, 0, 1],  # w  v
        ],
        hand=tournament_starting_now,
    )


def test_52_cards_played(tournament_starting_now: Hand) -> None:
    play_out_hand(tournament_starting_now)

    expect_visibility(
        [
            # Eva buddy see eva thang.
            # n, e, s, w <-- viewers
            [1, 1, 1, 1],  # n seat
            [1, 1, 1, 1],  # e  |
            [1, 1, 1, 1],  # s  | (dummy)
            [1, 1, 1, 1],  # w  v
        ],
        hand=tournament_starting_now,
    )


def expect_visibility(expectation_array, hand: Hand) -> None:
    __tracebackhide__ = True

    for viewer_letter, viewer in hand.players_by_direction_letter.items():
        viewer_index = "NESW".index(viewer_letter)
        for target_index, target_letter in enumerate("NESW"):
            actual = hand.board.can_see_cards_at(player=viewer, direction_letter=target_letter)
            expected = expectation_array[target_index][viewer_index]
            print(f"{viewer} {target_letter} {actual=} {expected=}")
            if actual != expected:
                pytest.fail(
                    f"{viewer} {'can' if actual else 'can not'} see {target_letter} but {'should not' if actual else 'should'}",
                )
