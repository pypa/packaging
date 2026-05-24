from __future__ import annotations

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Any, TypeVar

    F = TypeVar("F", bound="Callable[..., Any]")


def add_attributes(**attrs: object) -> Callable[[F], F]:
    def decorator(func: F) -> F:
        for name, value in attrs.items():
            setattr(func, name, value)
        return func

    return decorator
