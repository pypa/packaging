from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable

F = TypeVar("F", bound="Callable[..., Any]")


def add_attributes(**attrs: object) -> Callable[[F], F]:
    def decorator(func: F) -> F:
        for name, value in attrs.items():
            setattr(func, name, value)
        return func

    return decorator
