import bridge.contract
import bridge.table

import app.models
from app.models.utils import assert_type


def set_auction_to(bid: bridge.contract.Bid, hand: app.models.Hand) -> app.models.Hand:
    assert_type(hand, app.models.Hand)

    def next_caller(current_caller: bridge.table.Player) -> bridge.table.Player:
        libTable = hand.auction.table
        return libTable.get_lho(current_caller)

    assert len(hand.auction.player_calls) == 0

    caller = hand.auction.allowed_caller()

    hand.add_call_from_player(player=caller, call=bid)
    assert len(hand.auction.player_calls) == 1
    caller = next_caller(caller)

    hand.add_call_from_player(player=caller, call=bridge.contract.Pass)
    assert len(hand.auction.player_calls) == 2
    caller = next_caller(caller)

    hand.add_call_from_player(player=caller, call=bridge.contract.Pass)
    assert len(hand.auction.player_calls) == 3
    caller = next_caller(caller)

    hand.add_call_from_player(player=caller, call=bridge.contract.Pass)
    assert len(hand.auction.player_calls) == 4
    assert hand.auction.found_contract

    return hand


def play_to_completion(h: app.models.Hand) -> None:
    while True:
        cc_bs = h.current_cards_by_seat()
        x = h.get_xscript()

        legal_cards = sorted(
            x.legal_cards(some_hand=bridge.table.Hand(cards=list(cc_bs[x.named_seats[0].seat])))
        )

        if not legal_cards:
            assert h.is_complete
            break

        assert h.player_who_may_play is not None, f"{h=} has nobody who can play?"

        h.add_play_from_player(
            player=h.player_who_may_play.libraryThing(hand=h),
            card=legal_cards[0],
        )
