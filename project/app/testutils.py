import bridge.contract

import app.models


def set_auction_to(bid: bridge.contract.Bid, table: app.models.Table) -> app.models.Table:
    def next_caller(current_caller):
        libTable = table.current_hand.auction.table
        return libTable.get_lho(current_caller)

    caller = table.current_hand.auction.allowed_caller()

    table.current_hand.add_call_from_player(player=caller, call=bid)
    table = app.models.Table.objects.get(pk=table.pk)
    caller = next_caller(caller)

    table.current_hand.add_call_from_player(player=caller, call=bridge.contract.Pass)
    table = app.models.Table.objects.get(pk=table.pk)
    caller = next_caller(caller)

    table.current_hand.add_call_from_player(player=caller, call=bridge.contract.Pass)
    table = app.models.Table.objects.get(pk=table.pk)
    caller = next_caller(caller)

    table.current_hand.add_call_from_player(player=caller, call=bridge.contract.Pass)
    table = app.models.Table.objects.get(pk=table.pk)
    assert table.current_auction.found_contract

    return table
