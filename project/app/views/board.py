from __future__ import annotations

import operator

from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse

import app.models
from app.views.misc import AuthedHttpRequest, logged_in_as_player_required


@logged_in_as_player_required()
def board_archive_view(request: AuthedHttpRequest, pk: int) -> TemplateResponse:
    board: app.models.Board = get_object_or_404(app.models.Board, pk=pk)
    player = request.user.player
    assert player is not None
    my_hand = player.hand_at_which_board_was_played(board)

    annotated_hands: list[app.models.Hand] = []

    h: app.models.Hand
    for h in board.hand_set.all():
        h.summary_for_this_viewer, h.score_for_this_viewer = h.summary_as_viewed_by(
            as_viewed_by=getattr(request.user, "player", None)
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
            "board": board,
            "my_hand_pk": my_hand.pk if my_hand is not None else None,
            "annotated_hands": sorted(
                annotated_hands,
                key=lambda s: numberify_score(operator.attrgetter("score_for_this_viewer")(s)),
                reverse=True,
            ),
        },
    )


@logged_in_as_player_required()
def board_list_view(request: AuthedHttpRequest) -> TemplateResponse:
    board_list = app.models.Board.objects.nicely_ordered()
    tournament = request.GET.get("tournament")
    if tournament is not None:
        board_list = board_list.filter(tournament=tournament)

    per_page = request.GET.get("per_page", 16)
    paginator = Paginator(board_list, per_page)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    context = {
        "page_obj": page_obj,
        "total_count": app.models.Board.objects.count(),
    }
    if tournament is not None:
        context |= {"tournament": tournament}

    return TemplateResponse(request=request, template="board_list.html", context=context)


@logged_in_as_player_required()
def tournament_list_view(request: AuthedHttpRequest) -> TemplateResponse:
    tournament_list = app.models.Tournament.objects.order_by("pk")

    context = {"tournament_list": tournament_list}

    return TemplateResponse(request=request, template="tournament_list.html", context=context)
