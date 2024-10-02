import bridge.seat
from bridge.auction import Auction
from django.http import HttpResponse, HttpResponseNotFound
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse

import app.models
from app.views.misc import AuthedHttpRequest, logged_in_as_player_required

from .details import _four_hands_context_for_table


@logged_in_as_player_required()
def archive_view(request: AuthedHttpRequest, pk: int) -> HttpResponse:
    t: app.models.Table = get_object_or_404(app.models.Table, pk=pk)

    board = t.current_board
    player = request.user.player

    assert player is not None

    if player.most_recent_seat is None:
        return TemplateResponse(
            request,
            "403.html",
            context={
                "explanation": f"You, {player.name}, have never been seated, hence cannot look at the cards"
            },
            status=403,
        )

    if not player.most_recent_seat.table.hand_set.filter(board=board).exists():
        return TemplateResponse(
            request,
            "403.html",
            context={"explanation": f"You, {player.name}, have not played board {board.pk}"},
            status=403,
        )

    a = t.current_auction
    c = a.status
    if c is Auction.Incomplete:
        return HttpResponseNotFound(f"Table {pk} has not found a contract")

    if c is Auction.PassedOut:
        context = _four_hands_context_for_table(request, t, as_dealt=True)
        context |= {
            "score": 0,
            "vars_score": {"passed_out": 0},
            "show_auction_history": False,
        }
        return TemplateResponse(
            request,
            "table_archive.html",
            context=context,
        )

    h = t.current_hand
    b = h.board
    declarer_vulnerable = a.declarer is not None and (
        b.ns_vulnerable
        and a.declarer.seat in (bridge.seat.Seat.NORTH, bridge.seat.Seat.SOUTH)
        or b.ew_vulnerable
        and a.declarer.seat in (bridge.seat.Seat.EAST, bridge.seat.Seat.WEST)
    )
    broken_down_score = h.xscript.final_score(declarer_vulnerable=declarer_vulnerable)
    if broken_down_score is None:
        return HttpResponseNotFound(
            f"The hand at table {t} has not been completely played, so there is no final score"
        )

    score_description = f"declarers got {broken_down_score.total} or I suppose you could say defenders got {-broken_down_score.total}"

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
