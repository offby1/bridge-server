import json

from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404

from app.models import Table


def table_json_view(request: HttpRequest, pk: int) -> HttpResponse:
    table = get_object_or_404(Table, pk=pk)
    # all our caller cares about is the current_hand pk
    payload = {"current_hand_pk": table.current_hand.pk}
    return HttpResponse(json.dumps(payload), headers={"Content-Type": "text/json"})
