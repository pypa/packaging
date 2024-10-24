from __future__ import annotations

import contextlib
import dataclasses
import sys
import typing

if typing.TYPE_CHECKING:
    from typing import Any

__all__ = ["ConfigurationError", "ConfigurationWarning", "ExceptionGroup"]


def __dir__() -> list[str]:
    return __all__


if sys.version_info >= (3, 11):  # pragma: no cover
    from builtins import ExceptionGroup
else:  # pragma: no cover

    class ExceptionGroup(Exception):
        """A minimal implementation of :external:exc:`ExceptionGroup` from Python 3.11.

        If :external:exc:`ExceptionGroup` is already defined by Python itself,
        that version is used instead.
        """

        message: str
        exceptions: list[Exception]

        def __init__(self, message: str, exceptions: list[Exception]) -> None:
            self.message = message
            self.exceptions = exceptions

        def __repr__(self) -> str:
            return f"{self.__class__.__name__}({self.message!r}, {self.exceptions!r})"


@dataclasses.dataclass(slots=True)
class _ErrorCollector:
    """
    Collect errors into ExceptionGroups.

    Used like this:

        collector = _ErrorCollector()
        # Add a single exception
        collector.error(ValueError("one"))

        # Supports nesting, including combining ExceptionGroups
        with collector.collect():
            raise ValueError("two")
        collector.finalize("Found some errors")

    Since making a collector and then calling finalize later is a common pattern,
    a convenience method ``on_exit`` is provided.
    """

    errors: list[Exception] = dataclasses.field(default_factory=list, init=False)

    def finalize(self, msg: str) -> None:
        """Raise a group exception if there are any errors."""
        if self.errors:
            raise ExceptionGroup(msg, self.errors)

    @contextlib.contextmanager
    def on_exit(self, msg: str) -> typing.Generator[_ErrorCollector]:
        """
        Calls finalize if no uncollected errors were present.

        Uncollected errors are raised normally.
        """
        yield self
        self.finalize(msg)

    @contextlib.contextmanager
    def collect(self, *err_cls: type[Exception]) -> typing.Generator[None]:
        """
        Context manager to collect errors into the error list.

        Must be inside loops, as only one error can be collected at a time.
        """
        error_classes = err_cls or (Exception,)
        try:
            yield
        except ExceptionGroup as error:
            self.errors.extend(error.exceptions)
        except error_classes as error:
            self.errors.append(error)

    def error(
        self,
        error: Exception,
    ) -> None:
        """Add an error to the list."""
        self.errors.append(error)


class ConfigurationError(Exception):
    """
    Error in the backend metadata. Has an optional key attribute, which will be
    non-None if the error is related to a single key in the pyproject.toml
    file.
    """

    def __init__(self, msg: str, *, key: str | None = None):
        super().__init__(msg)
        self._key = key

    @property
    def key(self) -> str | None:  # pragma: no cover
        return self._key


class ConfigurationWarning(UserWarning):
    """Warnings about backend metadata."""


class ErrorCollector(_ErrorCollector):
    """
    An error collector that also can build :class:`ConfigurationError`.
    """

    def config_error(
        self,
        msg: str,
        *,
        key: str | None = None,
        got: Any = None,
        got_type: type[Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Add a configuration error to the error list."""
        msg = msg.format(key=f'"{key}"', **kwargs)
        if got is not None:
            msg = f"{msg} (got {got!r})"
        if got_type is not None:
            msg = f"{msg} (got {got_type.__name__})"

        self.errors.append(ConfigurationError(msg, key=key))
