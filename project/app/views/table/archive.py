from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse

from app.models import Table


def archive_view(request, pk):
    t = get_object_or_404(Table, pk=pk)
    return TemplateResponse(
        request,
        "table_archive.html",
        context={
            "table": t,
            "show_auction_history": True,
        },
    )
