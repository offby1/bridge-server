from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

import app.models


def hand_list_view(request: HttpRequest) -> HttpResponse:
    hand_list = (
        app.models.Hand.objects.all()
    )  # TODO -- filter to those that should be visible by request.user
    paginator = Paginator(hand_list, 15)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)
    context = {
        "page_obj": page_obj,
        "total_count": app.models.Hand.objects.count(),
    }

    return render(request, "hand_list.html", context=context)
