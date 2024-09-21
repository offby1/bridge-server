import bridge.seat
from bridge.auction import Contract
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse

import app.models

from .details import _four_hands_context_for_table


def archive_view(request, pk):
    t = get_object_or_404(app.models.Table, pk=pk)
    a = t.current_auction
    c = a.status
    assert isinstance(c, Contract)
    h = t.current_action
    b = h.board
    declarer_vulnerable = (
        b.ns_vulnerable
        and a.declarer.seat in (bridge.seat.Seat.NORTH, bridge.seat.Seat.SOUTH)
        or b.ew_vulnerable
        and a.declarer.seat in (bridge.seat.Seat.EAST, bridge.seat.Seat.WEST)
    )
    broken_down_score = h.xscript.final_score(declarer_vulnerable=declarer_vulnerable)
    assert broken_down_score is not None
    score_description = f"declarers got {broken_down_score.total} or I suppose you could say defenders got {-broken_down_score.total}"
    print(f"{score_description=}")
    context = _four_hands_context_for_table(request, t, as_dealt=True)
    context |= {
        "score": score_description,
        "vars_score": vars(broken_down_score),
        "show_auction_history": True,
    }
    return TemplateResponse(
        request,
        "table_archive.html",
        context=context,
    )
