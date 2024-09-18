from bridge.card import Suit
from bridge.contract import Bid
from bridge.seat import Seat

from .models import Table
from .testutils import set_auction_to


def test_table_dataclass_thingy(usual_setup: None) -> None:
    t = Table.objects.first()
    assert t is not None
    set_auction_to(
        Bid(level=1, denomination=Suit.CLUBS), t
    )
    assert t.current_auction.declarer.seat == Seat.NORTH

    ds = t.display_skeleton()
    for dir_ in Seat:
        assert ds[dir_].textual_summary == "13 cards"

    assert not ds[Seat.NORTH].this_hands_turn_to_play
    assert ds[Seat.EAST].this_hands_turn_to_play
    assert not ds[Seat.SOUTH].this_hands_turn_to_play
    assert not ds[Seat.WEST].this_hands_turn_to_play
