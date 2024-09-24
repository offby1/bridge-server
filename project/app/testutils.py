import bridge.contract

import app.models


def set_auction_to(bid: bridge.contract.Bid, table: app.models.Table) -> None:
    def next_caller(current_caller):
        libTable = table.current_hand.auction.table
        return libTable.get_lho(current_caller)

    caller = table.current_hand.auction.allowed_caller()

    print(f"{len(table.current_hand.auction.player_calls)}")
    table.current_hand.add_call_from_player(player=caller, call=bid)
    caller = next_caller(caller)

    print(f"{len(table.current_hand.auction.player_calls)}")
    table.current_hand.add_call_from_player(player=caller, call=bridge.contract.Pass)
    caller = next_caller(caller)

    print(f"{len(table.current_hand.auction.player_calls)}")
    table.current_hand.add_call_from_player(player=caller, call=bridge.contract.Pass)
    caller = next_caller(caller)

    print(f"{len(table.current_hand.auction.player_calls)}")
    table.current_hand.add_call_from_player(player=caller, call=bridge.contract.Pass)
