import bridge.card
import bridge.contract

from .models import Table, logged_queries


def test_auction_doesnt_do_a_shitton_of_queries(usual_setup) -> None:
    t = Table.objects.first()
    assert t is not None
    h = t.current_action

    def next_caller(current_caller):
        table = h.auction.table
        return table.get_lho(current_caller)

    caller = h.auction.allowed_caller()

    def c(call: bridge.contract.Call) -> None:
        nonlocal caller
        h.add_call_from_player(player=caller, call=call)
        caller = next_caller(caller)

    c(bridge.contract.Pass)
    c(bridge.contract.Pass)
    c(bridge.contract.Pass)
    c(bridge.contract.Bid(level=1, denomination=bridge.card.Suit.CLUBS))
    c(bridge.contract.Pass)
    c(bridge.contract.Pass)
    c(bridge.contract.Double)
    c(bridge.contract.Pass)
    c(bridge.contract.Pass)

    with logged_queries():
        h.auction
    assert "cat" == "dog"
