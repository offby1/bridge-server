import bridge.card
import bridge.contract

from .models import Hand, Player, Table, logged_queries
from .views.hand import hand_detail_view


def test_hand_detail_view_doesnt_do_a_shitton_of_queries(usual_setup, rf) -> None:
    t = Table.objects.first()
    assert t is not None
    h = t.current_hand

    def next_caller(current_caller):
        table = h.auction.table
        return table.get_lho(current_caller)

    caller = h.auction.allowed_caller()

    def c(call: bridge.contract.Call) -> None:
        nonlocal caller
        Hand.objects.get(pk=h.pk).add_call_from_player(player=caller, call=call)
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

    request = rf.get("/woteva/", data={"pk": t.pk})
    p = Player.objects.first()
    assert p is not None
    request.user = p.user

    # Note: I could also use https://pytest-django.readthedocs.io/en/latest/helpers.html#django-assert-max-num-queries
    with logged_queries() as ql:
        hand_detail_view(request, t.current_hand.pk)

    # Omit "select count" in the hope that those are somehow less expensive
    filtered_calls = [c for c in ql.calls if not c[0].startswith("SELECT COUNT(*)")]

    assert len(filtered_calls) <= 62
