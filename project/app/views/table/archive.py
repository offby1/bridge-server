from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse

from app.models import Table

from .details import _four_hands_context_for_table


def archive_view(request, pk):
    t = get_object_or_404(Table, pk=pk)
    context = _four_hands_context_for_table(request, t, as_dealt=True)
    context |= {
        "show_auction_history": True,
    }
    return TemplateResponse(
        request,
        "table_archive.html",
        context=context,
    )
