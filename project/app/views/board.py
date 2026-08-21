from __future__ import annotations

from typing import Any

import django_tables2 as tables
from django.conf import settings
from django.db.models.query import QuerySet
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import SafeString
from django_filters import FilterSet
from django_filters.views import FilterView

import app.models
import app.readers
from app.models.types import PK
from app.views.misc import make_tournament_filter_dropdown_list_items


def board_archive_view(request: HttpRequest, pk: PK) -> HttpResponse:
    board: app.models.Board = get_object_or_404(app.models.Board, pk=pk)
    # TODO -- this is too strict, and it is the last card-visibility check that doesn't
    # go through app/visibility.py.  `card_visibility_level` already gets the case this
    # gets wrong right: an anonymous visitor may see a completed tournament.
    if not request.user.is_authenticated and not board.tournament.is_complete:
        return HttpResponseRedirect(settings.LOGIN_URL + f"?next={request.path}")

    as_viewed_by: app.models.Player | None = None

    if request.user.is_authenticated:
        as_viewed_by = getattr(request.user, "player", None)

    annotated_hands = app.readers.get_board_archive_hands(board=board, as_viewed_by=as_viewed_by)

    return TemplateResponse(
        request=request,
        template="board_archive.html",
        context={
            "annotated_hands": annotated_hands,
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
    summary = tables.Column(empty_values=(), orderable=False)

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
        return super().get_context_data(**kwargs) | {
            "dropdown_list_items": make_tournament_filter_dropdown_list_items(
                self.request, "tournament__display_number"
            )
        }

    def get_queryset(self) -> QuerySet:
        return self.model.objects.nicely_ordered()
