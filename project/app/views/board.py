from __future__ import annotations

import operator

from django.conf import settings
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse

import app.models
from app.models.types import PK


def board_archive_view(request: HttpRequest, pk: PK) -> HttpResponse:
    board: app.models.Board = get_object_or_404(app.models.Board, pk=pk)
    # TODO -- this is too strict; re-use, (or duplicate) logic from app.views.hand._error_response_or_viewfunc
    if not request.user.is_authenticated and not board.tournament.is_complete:
        return HttpResponseRedirect(settings.LOGIN_URL + f"?next={request.path}")

    as_viewed_by: app.models.Player | None = None

    if request.user.is_authenticated:
        as_viewed_by = getattr(request.user, "player", None)

    annotated_hands: list[app.models.Hand] = []

    h: app.models.Hand
    for h in app.models.hand.enrich(board.hand_set.all()):
        h.dis_my_hand = False
        if as_viewed_by is not None:
            if as_viewed_by.pk in h.player_pks():
                h.dis_my_hand = True
                as_viewed_by.cache_set(board=board, hand=h)

        h.summary_for_this_viewer, h.score_for_this_viewer = h.summary_as_viewed_by(
            as_viewed_by=as_viewed_by
        )

        annotated_hands.append(h)

    def numberify_score(s: int | str) -> float:
        if isinstance(s, str):
            return float("-inf")
        return s

    return TemplateResponse(
        request=request,
        template="board_archive.html",
        context={
            "annotated_hands": sorted(
                annotated_hands,
                key=lambda s: numberify_score(operator.attrgetter("score_for_this_viewer")(s)),
                reverse=True,
            ),
            "board": board,
            "viewer_played_this_board": any(h.dis_my_hand for h in annotated_hands),
        },
    )


def board_list_view(request: HttpRequest) -> TemplateResponse:
    board_list = app.models.Board.objects.nicely_ordered()
    tournament = request.GET.get("tournament")
    if tournament is not None:
        board_list = board_list.filter(tournament=tournament)

    per_page = request.GET.get("per_page", 16)
    paginator = Paginator(board_list, per_page)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    context = {
        "filtered_count": paginator.count,
        "page_obj": page_obj,
    }
    if tournament is not None:
        context |= {"tournament": tournament}

    return TemplateResponse(request=request, template="board_list.html", context=context)
