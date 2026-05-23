# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.
"""Version helpers shared between :mod:`packaging.ranges` and
:mod:`packaging.specifiers`.

This module is private to :mod:`packaging`; the names in ``__all__``
form the public contract for the in-package callers.
"""

from __future__ import annotations

from .version import InvalidVersion, Version

__all__ = ["coerce_version", "trim_release"]


def __dir__() -> list[str]:
    return __all__


def trim_release(release: tuple[int, ...]) -> tuple[int, ...]:
    """Strip trailing zeros from a release tuple."""
    end = len(release)
    while end > 1 and release[end - 1] == 0:
        end -= 1
    return release if end == len(release) else release[:end]


def coerce_version(version: Version | str) -> Version | None:
    """Parse *version*; ``None`` if invalid."""
    if not isinstance(version, Version):
        try:
            version = Version(version)
        except InvalidVersion:
            return None
    return version
