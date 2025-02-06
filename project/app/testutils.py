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
    assert caller is not None

    hand.add_call_from_player(player=caller, call=bid)
    assert len(hand.auction.player_calls) == hand.call_set.count() == 1
    caller = next_caller(caller)

    hand.add_call_from_player(player=caller, call=bridge.contract.Pass)
    assert len(hand.auction.player_calls) == hand.call_set.count() == 2
    caller = next_caller(caller)

    hand.add_call_from_player(player=caller, call=bridge.contract.Pass)
    assert len(hand.auction.player_calls) == hand.call_set.count() == 3
    caller = next_caller(caller)

    hand.add_call_from_player(player=caller, call=bridge.contract.Pass)
    assert len(hand.auction.player_calls) == hand.call_set.count() == 4
    assert hand.auction.found_contract

    return hand


def play_out_hand(t: app.models.Table) -> None:
    h = t.current_hand

    while (p := h.player_who_may_call) is not None:
        call = h.get_xscript().auction.legal_calls()[0]
        print(f"{p} calls {call}")
        h.add_call_from_player(player=p.libraryThing(), call=call)
    while (p := h.player_who_may_play) is not None:
        play = h.get_xscript().slightly_less_dumb_play()
        h.add_play_from_player(player=p.libraryThing(), card=play.card)
        print(f"{p} plays {play}")
        h.get_xscript().add_card(play.card)
