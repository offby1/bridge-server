from typing import Any

from django.http import HttpRequest, HttpResponse
from django.views.generic import View
from django.views.generic.list import (
    MultipleObjectMixin,
    MultipleObjectTemplateResponseMixin,
)

from .filterset import FilterSet

class FilterMixin:
    filterset_class: type[FilterSet] | None
    filterset_fields: Any
    strict: bool
    def get_filterset_class(self) -> type[FilterSet]: ...
    def get_filterset(self, filterset_class: type[FilterSet]) -> FilterSet: ...
    def get_filterset_kwargs(self, filterset_class: type[FilterSet]) -> dict[str, Any]: ...
    def get_strict(self) -> bool: ...

class BaseFilterView(FilterMixin, MultipleObjectMixin, View):
    filterset: FilterSet
    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse: ...

class FilterView(MultipleObjectTemplateResponseMixin, BaseFilterView):
    template_name_suffix: str
