import pytest
from bridge.card import Card, Suit
from bridge.contract import Bid, Pass
from bridge.seat import Seat

from .models import Player, Table
from .testutils import set_auction_to
from .views.hand import _display_and_control


def test_table_dataclass_thingy(usual_setup: None) -> None:
    t = Table.objects.first()
    assert t is not None
    set_auction_to(Bid(level=1, denomination=Suit.CLUBS), t.current_hand)
    assert t.current_auction.declarer.seat == Seat.NORTH

    ds = t.current_hand.display_skeleton()
    for dir_ in Seat:
        assert ds[dir_].textual_summary == "13 cards"

    assert not ds[Seat.NORTH].this_hands_turn_to_play
    assert ds[Seat.EAST].this_hands_turn_to_play
    assert not ds[Seat.SOUTH].this_hands_turn_to_play
    assert not ds[Seat.WEST].this_hands_turn_to_play


def test_hand_controlability(usual_setup: None, settings) -> None:
    t = Table.objects.first()
    assert t is not None

    def expect_controlability(expectation_array):
        for seat in t.current_hand.players_by_direction:
            for viewer in t.current_hand.players_by_direction:
                actual = _display_and_control(
                    hand=t.current_hand,
                    seat=Seat(seat),
                    as_viewed_by=t.current_hand.players_by_direction[viewer],
                    as_dealt=False,
                )
                seat_index = "NESW".index(seat)
                viewer_index = "NESW".index(viewer)
                assert (
                    actual["viewer_may_control_this_seat"]
                    == expectation_array[seat_index][viewer_index]
                ), f"{t.current_hand.players_by_direction[viewer]} {'can' if actual['viewer_may_control_this_seat'] else 'can not'} control {seat=} "

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

    set_auction_to(Bid(level=1, denomination=Suit.CLUBS), t.current_hand)
    assert str(t.current_hand.auction.status) == "one Club played by Jeremy Northam, sitting North"

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
    t.current_hand.add_play_from_player(
        player=t.current_hand.players_by_direction[Seat.EAST.value].libraryThing(),
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


def test_rejects_calls_after_auction_is_settled(usual_setup) -> None:
    t = Table.objects.first()
    assert t is not None

    set_auction_to(Bid(level=1, denomination=Suit.CLUBS), t.current_hand)

    # Not legal because the auction is over
    with pytest.raises(Exception):
        t.current_had.add_call_from_player(player=Player.objects.first(), call=Pass)
