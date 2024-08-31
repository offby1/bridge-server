from typing import Any, Type


def assert_type(obj_: Any, expected_type: Type[Any]) -> None:
    assert isinstance(
        obj_, expected_type
    ), f"I want a {expected_type} but you done gimme a {type(obj_)}"
