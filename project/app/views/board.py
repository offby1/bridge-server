from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse

import app.models
from app.views.misc import AuthedHttpRequest, logged_in_as_player_required


@logged_in_as_player_required()
def board_archive_view(request: AuthedHttpRequest, board_pk: str) -> TemplateResponse:
    board: app.models.Board = get_object_or_404(app.models.Board, pk=board_pk)

    annotated_hands: list[app.models.Hand] = []

    h: app.models.Hand
    for h in board.hand_set.all():
        h.summary_for_this_viewer = h.summary_as_viewed_by(
            as_viewed_by=getattr(request.user, "player", None)
        )
        annotated_hands.append(h)
    return TemplateResponse(
        request=request,
        template="board_archive.html",
        context={"board": board, "annotated_hands": annotated_hands},
    )


@logged_in_as_player_required()
def board_list_view(request: AuthedHttpRequest) -> TemplateResponse:
    board_list = app.models.Board.objects.order_by("id").all()
    paginator = Paginator(board_list, 15)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)
    b: app.models.Board

    context = {
        "page_obj": page_obj,
        "total_count": app.models.Board.objects.count(),
    }

    return TemplateResponse(request=request, template="board_list.html", context=context)
