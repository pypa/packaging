from __future__ import annotations

import contextlib
import dataclasses
import sys
import typing

if typing.TYPE_CHECKING:
    from collections.abc import Generator
    from typing import Any

__all__ = ["ConfigurationError", "ConfigurationWarning", "ExceptionGroup"]


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


@dataclasses.dataclass
class ErrorCollector:
    """
    Collect errors and raise them as a group at the end (if collect_errors is True),
    otherwise raise them immediately.
    """

    errors: list[Exception] = dataclasses.field(default_factory=list)

    def config_error(
        self,
        msg: str,
        *,
        key: str | None = None,
        got: Any = None,
        got_type: type[Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Raise a configuration error, or add it to the error list."""
        msg = msg.format(key=f'"{key}"', **kwargs)
        if got is not None:
            msg = f"{msg} (got {got!r})"
        if got_type is not None:
            msg = f"{msg} (got {got_type.__name__})"

        self.errors.append(ConfigurationError(msg, key=key))

    def finalize(self, msg: str) -> None:
        """Raise a group exception if there are any errors."""
        if self.errors:
            raise ExceptionGroup(msg, self.errors)

    @contextlib.contextmanager
    def collect(self) -> Generator[None, None, None]:
        """Support nesting; add any grouped errors to the error list."""
        try:
            yield
        except ExceptionGroup as error:
            self.errors.extend(error.exceptions)
