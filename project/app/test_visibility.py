import datetime
from typing import Generator

import freezegun
import pytest

from app.models import Board, Hand, Player, Tournament
from app.models.tournament import check_for_expirations
from bridge.card import Suit
from bridge.contract import Bid
from bridge.seat import Seat as libSeat

from .testutils import find_incomplete_hand, play_out_hand, set_auction_to


@pytest.fixture
def completed_tournament(nearly_completed_tournament: Tournament) -> Hand:
    # Complete that tournament!
    hand: Hand | None = Hand.objects.first()
    assert hand is not None

    while True:
        play_out_hand(hand)

    assert hand.tournament.is_complete
    return hand


def test_completed_tournament(completed_tournament) -> None:
    table = completed_tournament
    non_tournament_player = Player.objects.create_synthetic()

    # ok now try various flavors of player
    for player in [None, table.tournament.seated_players().first(), non_tournament_player]:
        for board in table.tournament.board_set.all():
            for direction in libSeat:
                assert board.can_see_cards_at(
                    player=player,
                    direction_letter=direction.value,
                ), f"Uh, {player} can't see {board} at {direction}?!"


def test_running_tournament_irrelevant_players(nearly_completed_tournament) -> None:
    hand = find_incomplete_hand(nearly_completed_tournament)
    assert hand is not None

    assert not hand.tournament.is_complete
    assert not hand.is_complete

    non_tournament_player = Player.objects.create_synthetic()

    for player in [None, non_tournament_player]:
        board: Board = hand.board
        for direction in libSeat:
            if player is not None and hand.dummy == hand.libPlayers_by_libSeat[direction]:
                assert board.can_see_cards_at(
                    player=player,
                    direction_letter=direction.value,
                ), f"Whoa -- {player} can't see the dummy at {board}?!"
            else:
                assert not board.can_see_cards_at(
                    player=player,
                    direction_letter=direction.value,
                ), f"Whoa -- {player} can see {board} at {direction}?!"


def test_running_tournament_relevant_player_not_yet_played_board(
    nearly_completed_tournament,
) -> None:
    hand: Hand | None = Hand.objects.first()
    assert hand is not None

    for player in Player.objects.all():
        for board in Board.objects.all():
            hand = player.hand_at_which_board_was_played(board)
            if hand is None:
                for direction in libSeat:
                    assert not board.can_see_cards_at(
                        player=player,
                        direction_letter=direction.value,
                    ), f"Whoa -- {player} can see {board} at {direction}?!"


def test_player_has_played_board(
    nearly_completed_tournament,
) -> None:
    for player in Player.objects.all():
        board: Board
        for board in Board.objects.all():
            hand: Hand = player.hand_at_which_board_was_played(board)

            if hand is None:
                continue

            for d_letter, p in hand.players_by_direction_letter.items():
                if p == player:
                    assert board.can_see_cards_at(
                        player=p,
                        direction_letter=d_letter,
                    ), f"Hey now -- {player} can't see their own cards ({board} at {d_letter})?!"


@pytest.fixture
def tournament_starting_now(fresh_tournament) -> Generator[Hand]:
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


def test_zero_cards_played(tournament_starting_now) -> None:
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


def test_one_card_played(tournament_starting_now) -> None:
    h: Hand = tournament_starting_now.current_hand
    set_auction_to(Bid(level=1, denomination=Suit.CLUBS), h)

    assert h.player_who_may_play is not None

    leader = h.player_who_may_play.libraryThing()
    libCard = h.get_xscript().slightly_less_dumb_play().card

    h.add_play_from_player(player=leader, card=libCard)

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


def test_52_cards_played(tournament_starting_now) -> None:
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

    seats = hand.current_seats()

    for seat in seats:
        seat_index = "NESW".index(seat.direction)

        for viewer_index, viewer in enumerate([s.player for s in seats]):
            actual = hand.current_hand.board.can_see_cards_at(
                player=viewer, direction_letter=seat.direction
            )
            expected = expectation_array[seat_index][viewer_index]
            if actual != expected:
                pytest.fail(
                    f"{viewer} {'can' if actual else 'can not'} see {seat.direction} but {'should not' if actual else 'should'}",
                )
