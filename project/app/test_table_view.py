import pytest
from bridge.card import Card, Suit
from bridge.contract import Bid, Pass
from bridge.seat import Seat

from .models import Hand, Player
from .testutils import set_auction_to
from .views.hand import _display_and_control


def test_table_display_skeleton(usual_setup: Hand) -> None:
    h: Hand = usual_setup
    ds = h.display_skeleton()
    for dir_ in Seat:
        assert ds[dir_].textual_summary == "13 cards"

    assert not ds[Seat.NORTH].this_hands_turn_to_play
    assert ds[Seat.EAST].this_hands_turn_to_play
    assert not ds[Seat.SOUTH].this_hands_turn_to_play
    assert not ds[Seat.WEST].this_hands_turn_to_play


def expect_visibility(expectation_array, hand: Hand) -> None:
    for seat in hand.players_by_direction_letter:
        for viewer in hand.players_by_direction_letter:
            actual1 = _display_and_control(
                hand=hand,
                seat=Seat(seat),
                as_viewed_by=hand.players_by_direction_letter[viewer],
                as_dealt=False,
            )
            seat_index = "NESW".index(seat)
            viewer_index = "NESW".index(viewer)
            assert (
                actual1["display_cards"] == expectation_array[seat_index][viewer_index]
            ), f"{hand.players_by_direction_letter[viewer]} {'can' if actual1['display_cards'] else 'can not'} see {Seat(seat)} "


def test_hand_visibility_one(usual_setup: Hand, second_setup: Hand) -> None:
    h1 = usual_setup
    set_auction_to(Bid(level=1, denomination=Suit.CLUBS), h1)

    assert str(h1.auction.status) == "one Club played by Jeremy Northam, sitting North"

    h2 = second_setup
    set_auction_to(Bid(level=1, denomination=Suit.CLUBS), h2)

    expect_visibility(
        [
            # n, e, s, w
            [1, 0, 0, 0],  # n
            [0, 1, 0, 0],  # e
            [0, 0, 1, 0],  # s
            [0, 0, 0, 1],  # w
        ],
        hand=h1,
    )

    # Make the opening lead
    h1.add_play_from_player(
        player=h1.players_by_direction_letter[Seat.EAST.value].libraryThing(),
        card=Card.deserialize("D2"),
    )

    # Now the dummy (south) is visible
    expect_visibility(
        [
            # n, e, s, w <-- viewers
            [1, 0, 0, 0],  # n seat
            [0, 1, 0, 0],  # e
            [1, 1, 1, 1],  # s
            [0, 0, 0, 1],  # w
        ],
        hand=h1,
    )


def test_hand_visibility_two(two_boards_one_is_complete: Hand) -> None:
    h = two_boards_one_is_complete

    expect_visibility(
        [
            # n, e, s, w <-- viewers
            [1, 1, 1, 1],  # n seat
            [1, 1, 1, 1],  # e
            [1, 1, 1, 1],  # s
            [1, 1, 1, 1],  # w
        ],
        hand=h,
    )


def test_hand_controlability(usual_setup: Hand, settings) -> None:
    h = usual_setup

    def expect_controlability(expectation_array):
        for seat in h.players_by_direction_letter:
            for viewer in h.players_by_direction_letter:
                actual = _display_and_control(
                    hand=h,
                    seat=Seat(seat),
                    as_viewed_by=h.players_by_direction_letter[viewer],
                    as_dealt=False,
                )
                seat_index = "NESW".index(seat)
                viewer_index = "NESW".index(viewer)
                assert (
                    actual["viewer_may_control_this_seat"]
                    == expectation_array[seat_index][viewer_index]
                ), f"{h.players_by_direction_letter[viewer]} {'can' if actual['viewer_may_control_this_seat'] else 'can not'} control {seat=} "

    # Nobody can control any cards, since the auction isn't settled
    expect_controlability(
        [
            # n, e, s, w
            [0, 0, 0, 0],  # n
            [0, 0, 0, 0],  # e
            [0, 0, 0, 0],  # s
            [0, 0, 0, 0],  # w
        ]
    )

    set_auction_to(Bid(level=1, denomination=Suit.CLUBS), h)
    assert str(h.auction.status) == "one Club played by Jeremy Northam, sitting North"

    # Only opening leader can control his cards
    expect_controlability(
        [
            # n, e, s, w
            [0, 0, 0, 0],  # n
            [0, 1, 0, 0],  # e
            [0, 0, 0, 0],  # s
            [0, 0, 0, 0],  # w
        ]
    )

    # Make the opening lead
    h.add_play_from_player(
        player=h.players_by_direction_letter[Seat.EAST.value].libraryThing(),
        card=Card.deserialize("D2"),
    )

    # Now declarer (north) can control the dummy (south).
    expect_controlability(
        [
            # n, e, s, w <-- viewers
            [0, 0, 0, 0],  # n seat
            [0, 0, 0, 0],  # e
            [1, 0, 0, 0],  # s
            [0, 0, 0, 0],  # w
        ]
    )


def test_rejects_calls_after_auction_is_settled(usual_setup: Hand) -> None:
    h = usual_setup
    set_auction_to(Bid(level=1, denomination=Suit.CLUBS), h)

    # Not legal because the auction is over
    with pytest.raises(Exception):
        player = Player.objects.first()
        assert player is not None
        h.add_call_from_player(player=player, call=Pass)
