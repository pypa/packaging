# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.
"""Version helpers shared between :mod:`packaging.ranges` and
:mod:`packaging.specifiers`.

Private to :mod:`packaging`; the names in ``__all__`` form the contract
for in-package callers.
"""

from __future__ import annotations

from .version import CmpSuffix, InvalidVersion, Version

__all__ = ["coerce_version", "trim_release", "version_cmpkey"]

# Shape returned by :func:`version_cmpkey`; the non-local arm of
# :data:`~packaging.version.CmpKey`. ``CmpSuffix`` is reused from
# :mod:`packaging.version` so the suffix layout has a single source of truth.
_VersionCmpKey = tuple[int, tuple[int, ...], CmpSuffix]


def __dir__() -> list[str]:
    return __all__


def trim_release(release: tuple[int, ...]) -> tuple[int, ...]:
    """Strip all trailing zeros from a release tuple.

    Matches :meth:`Version._cmpkey`'s release form, so ``(0,)`` /
    ``(0, 0)`` collapse to ``()``.
    """
    end = len(release)
    while end and release[end - 1] == 0:
        end -= 1
    return release if end == len(release) else release[:end]


def version_cmpkey(version: Version) -> _VersionCmpKey:
    """Build the first three components of :meth:`Version._cmpkey` from
    public attributes.
    """
    release = trim_release(version.release)
    suffix: CmpSuffix

    if version.pre is None and version.post is None and version.dev is None:
        # No pre/post/dev: 3 sorts after a/b/rc, final 1 sorts after dev.
        suffix = (3, 0, 0, 0, 1, 0)
    elif version.pre is None and version.post is None:
        # Dev-only: -1 sorts before a/b/rc.
        suffix = (-1, 0, 0, 0, 0, version.dev or 0)
    elif version.pre is None:
        # No pre-release; post/dev fill the trailing slots.
        suffix = (
            3,
            0,
            1,
            version.post or 0,
            1 if version.dev is None else 0,
            version.dev or 0,
        )
    else:
        # Pre-release: 0/1/2 for a/b/rc, then post/dev.
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
    """Parse version into a :class:`Version`, or return ``None``.

    Returns ``None`` for any input that is not a :class:`Version` or
    valid version string, including ``None`` and other unexpected types.
    """
    if isinstance(version, Version):
        return version
    if not isinstance(version, str):
        return None
    try:
        return Version(version)
    except InvalidVersion:
        return None
