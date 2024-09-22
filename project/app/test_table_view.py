from bridge.card import Suit
from bridge.contract import Bid
from bridge.seat import Seat

from .models import Table
from .testutils import set_auction_to
from .views.table.details import _wat


def test_table_dataclass_thingy(usual_setup: None) -> None:
    t = Table.objects.first()
    assert t is not None
    set_auction_to(Bid(level=1, denomination=Suit.CLUBS), t)
    assert t.current_auction.declarer.seat == Seat.NORTH

    ds = t.display_skeleton()
    for dir_ in Seat:
        assert ds[dir_].textual_summary == "13 cards"

    assert not ds[Seat.NORTH].this_hands_turn_to_play
    assert ds[Seat.EAST].this_hands_turn_to_play
    assert not ds[Seat.SOUTH].this_hands_turn_to_play
    assert not ds[Seat.WEST].this_hands_turn_to_play


def test_hand_visibility(usual_setup: None, settings) -> None:
    t = Table.objects.first()
    assert t is not None
    set_auction_to(Bid(level=1, denomination=Suit.CLUBS), t)

    settings.POKEY_BOT_BUTTONS = False

    def expect_visibility(expecation_array):
        for seat in t.players_by_direction:
            for viewer in t.players_by_direction:
                actual = _wat(
                    table=t,
                    seat=Seat(seat),
                    as_viewed_by=t.players_by_direction[viewer],
                    as_dealt=False,
                )
                assert (
                    actual["display_cards"] == expecation_array[seat - 1][viewer - 1]
                ), f"{t.players_by_direction[viewer]} {'can' if actual['display_cards'] else 'can not'} see {seat=} "

    expect_visibility(
        [
            # n, e, s, w
            [1, 0, 0, 0],  # n
            [0, 1, 0, 0],  # e
            [0, 0, 1, 0],  # s
            [0, 0, 0, 1],  # w
        ]
    )
