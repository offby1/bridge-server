from typing import Any

from django.db.models import QuerySet

class FilterSet:
    class Meta: ...
    data: Any
    request: Any
    is_bound: bool
    qs: QuerySet[Any]
    queryset: QuerySet[Any]
    def is_valid(self) -> bool: ...
