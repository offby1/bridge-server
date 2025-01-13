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


def expect_visibility(expectation_array, table: Table) -> None:
    for seat in table.current_hand.players_by_direction:
        for viewer in table.current_hand.players_by_direction:
            actual1 = _display_and_control(
                hand=table.current_hand,
                seat=Seat(seat),
                as_viewed_by=table.current_hand.players_by_direction[viewer],
                as_dealt=False,
            )
            seat_index = "NESW".index(seat)
            viewer_index = "NESW".index(viewer)
            assert (
                actual1["display_cards"] == expectation_array[seat_index][viewer_index]
            ), f"{table.current_hand.players_by_direction[viewer]} {'can' if actual1['display_cards'] else 'can not'} see {Seat(seat)} "


def test_hand_visibility_one(usual_setup: None, second_setup: Table) -> None:
    t1 = Table.objects.first()
    assert t1 is not None
    set_auction_to(Bid(level=1, denomination=Suit.CLUBS), t1.current_hand)

    assert str(t1.current_auction.status) == "one Club played by Jeremy Northam, sitting North"

    t2 = second_setup
    set_auction_to(Bid(level=1, denomination=Suit.CLUBS), t2.current_hand)

    expect_visibility(
        [
            # n, e, s, w
            [1, 0, 0, 0],  # n
            [0, 1, 0, 0],  # e
            [0, 0, 1, 0],  # s
            [0, 0, 0, 1],  # w
        ],
        table=t1,
    )

    # Make the opening lead
    t1.current_hand.add_play_from_player(
        player=t1.current_hand.players_by_direction[Seat.EAST.value].libraryThing(),
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
        table=t1,
    )


def test_hand_visibility_two(played_to_completion: None) -> None:
    t2: Table | None = Table.objects.first()
    assert t2 is not None

    expect_visibility(
        [
            # n, e, s, w <-- viewers
            [1, 1, 1, 1],  # n seat
            [1, 1, 1, 1],  # e
            [1, 1, 1, 1],  # s
            [1, 1, 1, 1],  # w
        ],
        table=t2,
    )


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
