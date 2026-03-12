from typing import Any

class Column:
    def __init__(
        self,
        accessor: Any = ...,
        verbose_name: str | None = ...,
        orderable: bool | None = ...,
        empty_values: tuple[Any, ...] | None = ...,
        order_by: Any = ...,
        visible: bool = ...,
        **kwargs: Any,
    ) -> None: ...
