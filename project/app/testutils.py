from bridge.contract import Bid as libBid
from bridge.contract import Pass as libPass

from .models import Table


def set_auction_to(bid: libBid, table: Table) -> None:
    h = table.current_handrecord

    def next_caller(current_caller):
        table = h.auction.table
        return table.get_lho(current_caller)

    caller = h.auction.allowed_caller()
    h.add_call_from_player(player=caller, call=bid)
    caller = next_caller(caller)

    h.add_call_from_player(player=caller, call=libPass)
    caller = next_caller(caller)

    h.add_call_from_player(player=caller, call=libPass)
    caller = next_caller(caller)

    h.add_call_from_player(player=caller, call=libPass)
