from __future__ import annotations

import operator

from django.conf import settings
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.utils import timezone

import app.models
from app.views.misc import AuthedHttpRequest
from app.models.types import PK


def board_archive_view(request: HttpRequest, pk: PK) -> HttpResponse:
    board: app.models.Board = get_object_or_404(app.models.Board, pk=pk)
    if request.user.is_anonymous and not board.tournament.is_complete:
        return HttpResponseRedirect(settings.LOGIN_URL + f"?next={request.path}")

    my_hand = None

    if not request.user.is_anonymous:
        if (player := getattr(request.user, "player", None)) is not None:
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
        "page_obj": page_obj,
        "total_count": app.models.Board.objects.count(),
    }
    if tournament is not None:
        context |= {"tournament": tournament}

    return TemplateResponse(request=request, template="board_list.html", context=context)


def tournament_list_view(request: AuthedHttpRequest) -> TemplateResponse:
    tournament_list = app.models.Tournament.objects.order_by("pk")
    open_for_signups = request.GET.get("open_for_signups")

    if open_for_signups:
        now = timezone.now()
        tournament_list = tournament_list.filter(
            signup_deadline__gte=now
        )  # .filter(play_completion_deadline__gte=now)

    context = {"tournament_list": tournament_list, "description": "", "button": ""}

    if open_for_signups:
        context["description"] = "Open for signups"
        if not tournament_list.exists():
            context["button"] = "Oh I guess you need a 'Make a new Tournament' button"

    return TemplateResponse(request=request, template="tournament_list.html", context=context)
