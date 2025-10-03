from __future__ import annotations

import operator
from typing import Any

from django.conf import settings
from django.db.models.query import QuerySet
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import SafeString
from django_filters import FilterSet  # type: ignore[import-untyped]
from django_filters.views import FilterView  # type: ignore[import-untyped]
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
import django_tables2 as tables  # type: ignore[import-untyped]

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


class BoardFilter(FilterSet):
    class Meta:
        model = app.models.Board
        fields = ["tournament__display_number"]


class BoardTable(tables.Table):
    board_number = tables.Column(accessor=tables.A("display_number"), verbose_name="Board #")
    tournament_number = tables.Column(
        accessor=tables.A("tournament__display_number"), verbose_name="Tournament #"
    )
    summary = tables.Column(empty_values=())

    def render_summary(self, record) -> SafeString:
        return format_html(
            """<a href="{}">{}</a>""",
            reverse("app:board-archive", kwargs=dict(pk=record.pk)),
            record,
        )


class BoardListView(tables.SingleTableMixin, FilterView):
    filterset_class = BoardFilter
    model = app.models.Board
    table_class = BoardTable
    template_name = "board_list.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        original = super().get_context_data(**kwargs)
        option_elts = {
            "option_elts": [
                format_html(
                    """<option value="{}">{}</option>""",
                    tournament.display_number,
                    tournament,
                )
                for tournament in app.models.Tournament.objects.order_by("-display_number").all()
            ]
        }
        return original | option_elts

    def get_queryset(self) -> QuerySet:
        return self.model.objects.nicely_ordered()
