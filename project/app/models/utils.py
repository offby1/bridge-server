from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.contrib.auth.models import User

if TYPE_CHECKING:
    from . import player


def assert_type(obj_: Any, expected_type: type[Any]) -> None:
    __tracebackhide__ = True
    assert isinstance(obj_, expected_type), (
        f"I want a {expected_type} but you done gimme a {type(obj_)}"
    )


class UserMitPlaya(User):
    player: player.Player | None
