import json

from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404
from django_eventstream import get_current_event_id  # type: ignore[import-untyped]

from app.models import Table


def table_json_view(request: HttpRequest, pk: int) -> HttpResponse:
    table = get_object_or_404(Table, pk=pk)

    payload = {
        "current_hand_pk": table.current_hand.pk,
        "current_event_id": get_current_event_id([table.event_channel_name]),
    }
    return HttpResponse(json.dumps(payload), headers={"Content-Type": "text/json"})
