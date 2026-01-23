from __future__ import annotations

import contextlib
import dataclasses
import sys
import typing

__all__ = ["ErrorCollector", "ExceptionGroup"]


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


@dataclasses.dataclass
class ErrorCollector:
    """
    Collect errors.
    """

    errors: list[Exception] = dataclasses.field(default_factory=list, init=False)

    def finalize(self, msg: str) -> None:
        """Raise a group exception if there are any errors."""
        if self.errors:
            raise ExceptionGroup(msg, self.errors)

    @contextlib.contextmanager
    def collect(
        self, err_cls: type[Exception] = Exception
    ) -> typing.Generator[None, None, None]:
        """Collect errors into the error list. Must be inside loops."""
        try:
            yield
        except ExceptionGroup as error:
            self.errors.extend(error.exceptions)
        except err_cls as error:
            self.errors.append(error)

    def error(
        self,
        error: Exception,
    ) -> None:
        """Add an error to the list."""
        self.errors.append(error)
