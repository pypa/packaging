from __future__ import annotations

import dataclasses
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    if sys.version_info >= (3, 11):
        from typing import Self
    else:
        from typing_extensions import Self


def _json_dict_factory(data: list[tuple[str, Any]]) -> dict[str, Any]:
    return {key: value for key, value in data if value is not None}


class DirectUrlValidationError(Exception):
    """Raised when when input data is not spec-compliant."""

    context: str | None = None
    message: str

    def __init__(
        self,
        cause: str | Exception,
        *,
        context: str | None = None,
    ) -> None:
        if isinstance(cause, DirectUrlValidationError):
            if cause.context:
                self.context = (
                    f"{context}.{cause.context}" if context else cause.context
                )
            else:
                self.context = context
            self.message = cause.message
        else:
            self.context = context
            self.message = str(cause)

    def __str__(self) -> str:
        if self.context:
            return f"{self.message} in {self.context!r}"
        return self.message


@dataclass(frozen=True, kw_only=True)
class VcsInfo:
    vcs: str
    requested_revision: str | None = None
    commit_id: str

    @classmethod
    def _from_dict(cls, d: Mapping[str, Any]) -> Self: ...


@dataclass(frozen=True, kw_only=True)
class ArchiveInfo:
    hashes: Mapping[str, str] | None = None
    hash: str | None = None  # Deprecated, use `hashes` instead

    @classmethod
    def _from_dict(cls, d: Mapping[str, Any]) -> Self:
        ...
        # XXX validate hashes (see pylock)
        # XXX log a warning if `hash` is used (probably not useful by lack of context)?


@dataclass(frozen=True, kw_only=True)
class DirInfo:
    editable: bool = False

    @classmethod
    def _from_dict(cls, d: Mapping[str, Any]) -> Self: ...


@dataclass(frozen=True, kw_only=True)
class DirectUrl:
    url: str
    archive_info: ArchiveInfo | None = None
    vcs_info: VcsInfo | None = None
    dir_info: DirInfo | None = None
    subdirectory: Path | None = None

    @classmethod
    def _from_dict(cls, d: Mapping[str, Any]) -> Self:
        ...
        # XXX exactly one of vcs_info, archive_info, dir_info must be present
        # XXX subdirectory must be relative
        # XXX if dir_info is present, url scheme must be file://

    @classmethod
    def from_dict(cls, d: Mapping[str, Any], /) -> Self:
        return cls._from_dict(d)

    def to_dict(self) -> Mapping[str, Any]:
        return dataclasses.asdict(self, dict_factory=_json_dict_factory)

    def validate(self) -> None:
        """Validate the DirectUrl instance against the specification.

        Raises :class:`DirectUrlValidationError` otherwise.
        """
        self.from_dict(self.to_dict())
