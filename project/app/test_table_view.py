from bridge.card import Suit
from bridge.contract import Bid
from bridge.seat import Seat

from .models import Table
from .testutils import set_auction_to


def test_table_dataclass_thingy(usual_setup):
    t = Table.objects.first()
    set_auction_to(
        Bid(level=1, denomination=Suit.CLUBS), t
    )  # dealer is declarer, and North dealt this hand.  I just know :-)
    h = t.current_auction
    print(h.declarer)
    ds = t.display_skeleton()
    for dir_ in Seat:
        assert ds[dir_].textual_summary == "13 cards"

    assert ds[Seat.NORTH].our_turn_to_play
    assert not ds[Seat.EAST].our_turn_to_play
    assert not ds[Seat.SOUTH].our_turn_to_play
    assert not ds[Seat.WEST].our_turn_to_play
