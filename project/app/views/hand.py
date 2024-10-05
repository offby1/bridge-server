import bridge.seat
from bridge.auction import Auction
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse, HttpResponseNotFound, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.template.response import TemplateResponse
from django.urls import reverse
from django.views.decorators.gzip import gzip_page

import app.models
from app.views.misc import AuthedHttpRequest, logged_in_as_player_required


def hand_list_view(request: HttpRequest) -> HttpResponse:
    hand_list = (
        app.models.Hand.objects.all()
    )  # TODO -- filter to those that should be visible by request.user
    paginator = Paginator(hand_list, 15)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)
    context = {
        "page_obj": page_obj,
        "total_count": app.models.Hand.objects.count(),
    }

    return render(request, "hand_list.html", context=context)


@gzip_page
@logged_in_as_player_required()
def hand_archive_view(request: AuthedHttpRequest, pk: int) -> HttpResponse:
    h: app.models.Hand = get_object_or_404(app.models.Hand, pk=pk)

    board = h.board
    player = request.user.player

    assert player is not None

    a = h.auction
    c = a.status
    if c is Auction.Incomplete:
        return HttpResponseRedirect(reverse("app:table-detail", args=[h.table.pk]))

    if c is Auction.PassedOut:
        context = _four_hands_context_for_hand(request, h, as_dealt=True)
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

    declarer_vulnerable = a.declarer is not None and (
        board.ns_vulnerable
        and a.declarer.seat in (bridge.seat.Seat.NORTH, bridge.seat.Seat.SOUTH)
        or board.ew_vulnerable
        and a.declarer.seat in (bridge.seat.Seat.EAST, bridge.seat.Seat.WEST)
    )
    broken_down_score = h.xscript.final_score(declarer_vulnerable=declarer_vulnerable)

    if broken_down_score is None:
        return HttpResponseNotFound(
            f"The hand at {h.table} has not been completely played (only {len(h.xscript.tricks)} tricks), so there is no final score"
        )

    score_description = f"declarers got {broken_down_score.total} or I suppose you could say defenders got {-broken_down_score.total}"

    context = _four_hands_context_for_hand(request, h, as_dealt=True)
    context |= {
        "score": score_description,
        "vars_score": vars(broken_down_score),
        "show_auction_history": True,
    }
    return TemplateResponse(
        request,
        "hand_archive.html",
        context=context,
    )
