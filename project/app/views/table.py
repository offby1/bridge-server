from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse

from ..models import Table
from .misc import logged_in_as_player_required


def table_list_view(request):
    context = {
        "table_list": Table.objects.all(),
    }

    return TemplateResponse(request, "table_list.html", context=context)


@logged_in_as_player_required()
def table_detail_view(request, pk):
    table = get_object_or_404(Table, pk=pk)

    context = {
        "table": table,
        "show_cards_for": [request.user.username],
    }

    return TemplateResponse(request, "table_detail.html", context=context)
