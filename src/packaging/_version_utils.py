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

__all__ = ["coerce_version", "trim_release", "version_cmpkey"]

_VersionCmpSuffix = tuple[int, int, int, int, int, int]
_VersionCmpKey = tuple[int, tuple[int, ...], _VersionCmpSuffix]


def __dir__() -> list[str]:
    return __all__


def trim_release(release: tuple[int, ...]) -> tuple[int, ...]:
    """Strip trailing zeros from a release tuple."""
    end = len(release)
    while end > 1 and release[end - 1] == 0:
        end -= 1
    return release if end == len(release) else release[:end]


def version_cmpkey(
    version: Version,
) -> _VersionCmpKey:
    """Return the leading comparison key tuple used by Version._key."""
    release = trim_release(version.release)

    if version.pre is None and version.post is None and version.dev is None:
        # 3 = no pre-release, 0/0/0 = no post/dev, 1 = no-dev sorts after dev.
        suffix = (3, 0, 0, 0, 1, 0)
    elif version.pre is None and version.post is None and version.dev is not None:
        # -1 = dev-only, so it sorts before a/b/rc; the trailing 0s are
        # the missing post/dev counters.
        suffix = (-1, 0, 0, 0, 0, version.dev)
    elif version.pre is None:
        # 3 = no pre-release; post/dev are encoded in the last four slots.
        suffix = (
            3,
            0,
            1,
            version.post or 0,
            1 if version.dev is None else 0,
            version.dev or 0,
        )
    else:
        # 0/1/2 = a/b/rc, 1 = no post-release, 0 = has dev, 1/0 = dev counter.
        pre_rank = {"a": 0, "b": 1, "rc": 2}[version.pre[0]]
        suffix = (
            pre_rank,
            version.pre[1],
            1 if version.post is not None else 0,
            version.post or 0,
            1 if version.dev is None else 0,
            version.dev or 0,
        )

    return version.epoch, release, suffix


def coerce_version(version: Version | str) -> Version | None:
    """Parse *version*; ``None`` if invalid."""
    if not isinstance(version, Version):
        try:
            version = Version(version)
        except InvalidVersion:
            return None
    return version
