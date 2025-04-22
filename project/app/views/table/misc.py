from django.http import HttpRequest, HttpResponse

from app.models.types import PK
from app.views import NotFound


def table_json_view(request: HttpRequest, pk: PK) -> HttpResponse:
    return NotFound("TODO -- unimplemented")
