from django.core.paginator import Paginator
from django.template.response import TemplateResponse

import app.models


def board_archive_view(request, *args, **kwargs):
    return TemplateResponse(request=request, template="board_archive.html", context={})


def board_list_view(request, *args, **kwargs):
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
