# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.
"""Private version-range helpers used by :mod:`packaging.specifiers`."""

from __future__ import annotations

import enum
import functools
from typing import (
    TYPE_CHECKING,
    Any,
    Final,
)

from .version import InvalidVersion, Version

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator, Sequence
    from typing import Union

__all__ = [
    "FULL_RANGE",
    "filter_by_ranges",
    "intersect_ranges",
    "ranges_are_prerelease_only",
    "standard_ranges",
    "wildcard_ranges",
]

#: The smallest possible PEP 440 version. No valid version is less than this.
_MIN_VERSION: Final[Version] = Version("0.dev0")


class _BoundaryKind(enum.Enum):
    """Where a boundary marker sits in the version ordering."""

    AFTER_LOCALS = enum.auto()  # after V+local, before V.post0
    AFTER_POSTS = enum.auto()  # after V.postN, before next release


@functools.total_ordering
class _BoundaryVersion:
    """A point on the version line between two real PEP 440 versions.

    Relative to a base version V::

        V < V+local < AFTER_LOCALS(V) < V.post0 < AFTER_POSTS(V)

    AFTER_LOCALS is the upper bound of ``<=V``, ``==V``, ``!=V`` (no
    local), and the lower bound of the upper-side range of ``!=V``.
    AFTER_POSTS is the lower bound of ``>V`` (V final or pre-release),
    excluding V's post-releases per PEP 440.
    """

    __slots__ = (
        "_cached_dev",
        "_cached_epoch",
        "_cached_post",
        "_cached_pre",
        "_cached_trimmed_release",
        "_kind",
        "version",
    )

    def __init__(self, version: Version, kind: _BoundaryKind) -> None:
        self.version = version
        self._kind = kind
        self._cached_trimmed_release = trim_release(version.release)
        self._cached_epoch = version.epoch
        self._cached_pre = version.pre
        self._cached_post = version.post
        self._cached_dev = version.dev

    def _is_family(self, other: Version) -> bool:
        """Is ``other`` a version that this boundary sorts above?"""
        if other.epoch != self._cached_epoch:
            return False
        # Inline release-trim comparison: other.release matches the
        # trimmed release iff its leading slice is equal and any extra
        # components are zero. Avoids trim_release's tuple allocation.
        other_release = other.release
        trimmed_release = self._cached_trimmed_release
        trimmed_length = len(trimmed_release)
        if len(other_release) < trimmed_length:
            return False
        if other_release[:trimmed_length] != trimmed_release:
            return False
        for i in range(trimmed_length, len(other_release)):
            if other_release[i] != 0:
                return False
        if other.pre != self._cached_pre:
            return False
        if self._kind == _BoundaryKind.AFTER_LOCALS:
            # Local family: same public version, any local label.
            return other.post == self._cached_post and other.dev == self._cached_dev
        # Post family: V itself + any post-release of V.
        return other.dev == self._cached_dev or other.post is not None

    def __eq__(self, other: object) -> bool:
        if isinstance(other, _BoundaryVersion):
            return self.version == other.version and self._kind == other._kind
        return NotImplemented

    def __lt__(self, other: _BoundaryVersion | Version) -> bool:
        if isinstance(other, _BoundaryVersion):
            if self.version != other.version:
                return self.version < other.version
            return self._kind.value < other._kind.value  # pragma: no cover
        # boundary < other_version iff V < other AND other not in family.
        # The cheap V >= other path short-circuits before the family check.
        if not (self.version < other):
            return False
        return not self._is_family(other)

    def __gt__(self, other: _BoundaryVersion | Version) -> bool:
        # Defined directly to bypass functools.total_ordering's
        # NotImplemented round-trip on reflected ``Version < boundary``.
        if isinstance(other, _BoundaryVersion):
            if self.version != other.version:
                return self.version > other.version
            return self._kind.value > other._kind.value
        if self.version >= other:
            return True
        return self._is_family(other)

    def __hash__(self) -> int:
        return hash((self.version, self._kind))

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.version!r}, {self._kind.name})"


if TYPE_CHECKING:
    _VersionOrBoundary = Union[Version, _BoundaryVersion, None]


@functools.total_ordering
class _LowerBound:
    """Lower bound of a version range.

    A version *v* of ``None`` means unbounded below (-inf).
    At equal versions, ``[v`` sorts before ``(v`` because an inclusive
    bound starts earlier.
    """

    __slots__ = ("_above", "inclusive", "version")

    def __init__(self, version: _VersionOrBoundary, inclusive: bool) -> None:
        self.version = version
        self.inclusive = inclusive
        # Pre-bind a predicate "is parsed at or above this lower
        # bound?" for the hot filter / contains loops. One direct
        # call per check, no operator-dispatch chain.
        if version is None:
            self._above: Callable[[Version], bool] | None = None
        elif isinstance(version, _BoundaryVersion):
            # >V produces an AFTER_POSTS lower bound; the upper-side
            # range of !=V produces an AFTER_LOCALS lower bound.
            if version._kind == _BoundaryKind.AFTER_POSTS:
                self._above = _make_above_after_posts(version.version)
            else:
                self._above = _make_above_after_locals(version.version)
        elif inclusive:
            self._above = version.__le__
        else:
            self._above = version.__lt__

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, _LowerBound):
            return NotImplemented  # pragma: no cover
        return self.version == other.version and self.inclusive == other.inclusive

    def __lt__(self, other: _LowerBound) -> bool:
        if not isinstance(other, _LowerBound):  # pragma: no cover
            return NotImplemented
        # -inf < anything (except -inf itself).
        if self.version is None:
            return other.version is not None
        if other.version is None:
            return False
        if self.version != other.version:
            return self.version < other.version
        # [v < (v: inclusive starts earlier.
        return self.inclusive and not other.inclusive

    def __hash__(self) -> int:
        return hash((self.version, self.inclusive))

    def __repr__(self) -> str:
        bracket = "[" if self.inclusive else "("
        return f"<{self.__class__.__name__} {bracket}{self.version!r}>"


@functools.total_ordering
class _UpperBound:
    """Upper bound of a version range.

    A version *v* of ``None`` means unbounded above (+inf).
    At equal versions, ``v)`` sorts before ``v]`` because an exclusive
    bound ends earlier.
    """

    __slots__ = ("_below", "inclusive", "version")

    def __init__(self, version: _VersionOrBoundary, inclusive: bool) -> None:
        self.version = version
        self.inclusive = inclusive
        # Pre-bind a predicate "is parsed at or below this upper
        # bound?". See _LowerBound for the rationale.
        if version is None:
            self._below: Callable[[Version], bool] | None = None
        elif isinstance(version, _BoundaryVersion):
            # Standard specifiers only ever produce AFTER_LOCALS upper
            # bounds (from <=V / ==V / !=V with no local).
            if version._kind == _BoundaryKind.AFTER_LOCALS:
                self._below = _make_below_after_locals(version.version)
            else:  # pragma: no cover (AFTER_POSTS upper not produced by specifiers)
                self._below = version.__ge__
        elif inclusive:
            self._below = version.__ge__
        else:
            self._below = version.__gt__

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, _UpperBound):
            return NotImplemented  # pragma: no cover
        return self.version == other.version and self.inclusive == other.inclusive

    def __lt__(self, other: _UpperBound) -> bool:
        if not isinstance(other, _UpperBound):  # pragma: no cover
            return NotImplemented
        # Nothing < +inf (except +inf itself).
        if self.version is None:
            return False
        if other.version is None:
            return True
        if self.version != other.version:
            return self.version < other.version
        # v) < v]: exclusive ends earlier.
        return not self.inclusive and other.inclusive

    def __hash__(self) -> int:
        return hash((self.version, self.inclusive))

    def __repr__(self) -> str:
        bracket = "]" if self.inclusive else ")"
        return f"<{self.__class__.__name__} {self.version!r}{bracket}>"


if TYPE_CHECKING:
    #: A single contiguous version range, as a (lower, upper) pair.
    VersionRange = tuple[_LowerBound, _UpperBound]


_NEG_INF: Final[_LowerBound] = _LowerBound(None, False)
_POS_INF: Final[_UpperBound] = _UpperBound(None, False)
FULL_RANGE: Final[tuple[VersionRange]] = ((_NEG_INF, _POS_INF),)


def trim_release(release: tuple[int, ...]) -> tuple[int, ...]:
    """Strip trailing zeros from a release tuple for normalized comparison."""
    end = len(release)
    while end > 1 and release[end - 1] == 0:
        end -= 1
    return release if end == len(release) else release[:end]


def _next_prefix_dev0(version: Version) -> Version:
    """Smallest version in the next prefix: 1.2 -> 1.3.dev0."""
    release = (*version.release[:-1], version.release[-1] + 1)
    return Version.from_parts(epoch=version.epoch, release=release, dev=0)


def _base_dev0(version: Version) -> Version:
    """The .dev0 of a version's base release: 1.2 -> 1.2.dev0."""
    return Version.from_parts(epoch=version.epoch, release=version.release, dev=0)


def _coerce_version(version: Version | str) -> Version | None:
    if not isinstance(version, Version):
        try:
            version = Version(version)
        except InvalidVersion:
            return None
    return version


def _make_above_after_posts(version: Version) -> Callable[[Version], bool]:
    """Predicate ``parsed > AFTER_POSTS(V)`` for a lower bound.

    Per PEP 440, ``>V`` excludes V's post-releases unless V is itself
    a post-release. AFTER_POSTS sits above V and every V.postN (with
    or without local), and just below the next release.
    """
    version_ge = version.__ge__
    version_epoch = version.epoch
    version_pre = version.pre
    version_dev = version.dev
    version_release_trimmed = trim_release(version.release)
    trimmed_length = len(version_release_trimmed)

    def above(parsed: Version) -> bool:
        if version_ge(parsed):
            return False
        # parsed > V cmpkey-wise: above the boundary iff NOT in V's
        # post family.
        if parsed.epoch != version_epoch:
            return True
        parsed_release = parsed.release
        if len(parsed_release) < trimmed_length:
            return True
        if parsed_release[:trimmed_length] != version_release_trimmed:
            return True
        for i in range(trimmed_length, len(parsed_release)):
            if parsed_release[i] != 0:
                return True
        if parsed.pre != version_pre:
            return True
        # In post family iff: same dev as V (covers V itself + V+local),
        # or any post-release (covers V.postN + V.postN+local).
        if parsed.dev == version_dev or parsed.post is not None:
            return False
        # Different dev with no post means parsed sorts before V
        # cmpkey-wise, in which case version_ge returned True already.
        return False  # pragma: no cover

    return above


def _make_above_after_locals(version: Version) -> Callable[[Version], bool]:
    """Predicate ``parsed > AFTER_LOCALS(V)`` for a lower bound.

    Used by the upper-side range of ``!=V`` (when V has no local
    segment). AFTER_LOCALS sits above V and every ``V+local`` but
    just below ``V.post0``.
    """
    version_ge = version.__ge__
    version_epoch = version.epoch
    version_pre = version.pre
    version_post = version.post
    version_dev = version.dev
    version_release_trimmed = trim_release(version.release)
    trimmed_length = len(version_release_trimmed)

    def above(parsed: Version) -> bool:
        if version_ge(parsed):
            return False
        # parsed > V cmpkey-wise: above the boundary iff NOT in V's
        # local family (same public version, any local segment).
        if parsed.epoch != version_epoch:
            return True
        parsed_release = parsed.release
        if len(parsed_release) < trimmed_length:
            return True
        if parsed_release[:trimmed_length] != version_release_trimmed:
            return True
        for i in range(trimmed_length, len(parsed_release)):
            if parsed_release[i] != 0:
                return True
        if parsed.pre != version_pre:
            return True
        if parsed.post != version_post:
            return True
        return parsed.dev != version_dev

    return above


def _make_below_after_locals(version: Version) -> Callable[[Version], bool]:
    """Predicate ``parsed <= AFTER_LOCALS(V)`` for an upper bound.

    Used by ``<=V``, ``==V``, ``!=V`` (no local). ``parsed`` is at or
    below the boundary when it is at or below V cmpkey-wise, or when
    it is in V's local family.
    """
    version_ge = version.__ge__
    version_epoch = version.epoch
    version_pre = version.pre
    version_post = version.post
    version_dev = version.dev
    version_release_trimmed = trim_release(version.release)
    trimmed_length = len(version_release_trimmed)

    def below(parsed: Version) -> bool:
        if version_ge(parsed):
            return True
        # parsed > V cmpkey-wise: below the boundary iff in V's local
        # family.
        if parsed.epoch != version_epoch:
            return False
        parsed_release = parsed.release
        if len(parsed_release) < trimmed_length:
            return False
        if parsed_release[:trimmed_length] != version_release_trimmed:
            return False
        for i in range(trimmed_length, len(parsed_release)):
            if parsed_release[i] != 0:
                return False
        if parsed.pre != version_pre:
            return False
        if parsed.post != version_post:
            return False
        return parsed.dev == version_dev

    return below


def _range_is_empty(lower: _LowerBound, upper: _UpperBound) -> bool:
    """True when the range defined by *lower* and *upper* contains no versions."""
    if lower.version is None or upper.version is None:
        return False
    if lower.version == upper.version:
        return not (lower.inclusive and upper.inclusive)
    return lower.version > upper.version


def intersect_ranges(
    left: Sequence[VersionRange],
    right: Sequence[VersionRange],
) -> list[VersionRange]:
    """Intersect two sorted, non-overlapping range lists (two-pointer merge)."""
    result: list[VersionRange] = []
    left_index = right_index = 0
    while left_index < len(left) and right_index < len(right):
        left_lower, left_upper = left[left_index]
        right_lower, right_upper = right[right_index]

        lower = max(left_lower, right_lower)
        upper = min(left_upper, right_upper)

        if not _range_is_empty(lower, upper):
            result.append((lower, upper))

        # Advance whichever side has the smaller upper bound.
        if left_upper < right_upper:
            left_index += 1
        else:
            right_index += 1

    return result


def filter_by_ranges(
    ranges: Sequence[VersionRange],
    iterable: Iterable[Any],
    key: Callable[[Any], Version | str] | None,
    prereleases: bool | None,
) -> Iterator[Any]:
    """Filter *iterable* against precomputed version *ranges*.

    With ``prereleases=None``, the PEP 440 default applies: pre-releases
    are excluded unless no final matches, in which case buffered
    pre-releases come out at the end.
    """
    if prereleases is None:
        # PEP 440 default: yield finals immediately; buffer
        # pre-releases until at least one final has been emitted.
        prerelease_buffer: list[Any] = []
        found_final = False

        if len(ranges) == 1:
            lower, upper = ranges[0]
            above = lower._above
            below = upper._below
            for item in iterable:
                parsed = _coerce_version(item if key is None else key(item))
                if parsed is None:
                    continue
                if above is not None and not above(parsed):
                    continue
                if below is not None and not below(parsed):
                    continue
                if parsed.is_prerelease:
                    if not found_final:
                        prerelease_buffer.append(item)
                else:
                    found_final = True
                    yield item
            if not found_final:
                yield from prerelease_buffer
            return

        for item in iterable:
            parsed = _coerce_version(item if key is None else key(item))
            if parsed is None:
                continue
            for lower, upper in ranges:
                above = lower._above
                if above is not None and not above(parsed):
                    break
                below = upper._below
                if below is None or below(parsed):
                    if parsed.is_prerelease:
                        if not found_final:
                            prerelease_buffer.append(item)
                    else:
                        found_final = True
                        yield item
                    break
        if not found_final:
            yield from prerelease_buffer
        return

    exclude_prereleases = prereleases is False

    if len(ranges) == 1:
        # Hot path: most specifiers and small SpecifierSets reduce to
        # a single contiguous range.
        lower, upper = ranges[0]
        above = lower._above
        below = upper._below
        for item in iterable:
            parsed = _coerce_version(item if key is None else key(item))
            if parsed is None:
                continue
            if exclude_prereleases and parsed.is_prerelease:
                continue
            if above is not None and not above(parsed):
                continue
            if below is None or below(parsed):
                yield item
        return

    for item in iterable:
        parsed = _coerce_version(item if key is None else key(item))
        if parsed is None:
            continue
        if exclude_prereleases and parsed.is_prerelease:
            continue
        for lower, upper in ranges:
            above = lower._above
            if above is not None and not above(parsed):
                break
            below = upper._below
            if below is None or below(parsed):
                yield item
                break


def _lowest_release_at_or_above(
    value: _VersionOrBoundary,
) -> Version | None:
    """Smallest non-pre-release version at or above *value*, or None."""
    if value is None:
        return None
    if isinstance(value, _BoundaryVersion):
        inner_version = value.version
        if inner_version.is_prerelease:
            # AFTER_LOCALS(1.0a1) -> nearest non-pre is 1.0
            return inner_version.__replace__(pre=None, dev=None, local=None)
        # AFTER_LOCALS(1.0) -> nearest non-pre is 1.0.post0
        # AFTER_LOCALS(1.0.post0) -> nearest non-pre is 1.0.post1
        next_post = (inner_version.post + 1) if inner_version.post is not None else 0
        return inner_version.__replace__(post=next_post, local=None)
    if not value.is_prerelease:
        return value
    # Strip pre/dev to get the final or post-release form.
    return value.__replace__(pre=None, dev=None, local=None)


def ranges_are_prerelease_only(ranges: Sequence[VersionRange]) -> bool:
    """True when every range in *ranges* contains only pre-releases.

    Used to detect unsatisfiable specifier sets when ``prereleases=False``:
    if every range is pre-release-only, every contained version is excluded.
    """
    for lower, upper in ranges:
        nearest = _lowest_release_at_or_above(lower.version)
        if nearest is None:
            return False
        if upper.version is None or nearest < upper.version:
            return False
        if nearest == upper.version and upper.inclusive:
            return False
    return True


def wildcard_ranges(op: str, base: Version) -> list[VersionRange]:
    """Ranges for ==V.* and !=V.*.

    ==1.2.* -> [1.2.dev0, 1.3.dev0);  !=1.2.* -> complement.
    """
    lower = _base_dev0(base)
    upper = _next_prefix_dev0(base)
    if op == "==":
        return [(_LowerBound(lower, True), _UpperBound(upper, False))]
    # !=
    return [
        (_NEG_INF, _UpperBound(lower, False)),
        (_LowerBound(upper, True), _POS_INF),
    ]


def standard_ranges(op: str, version: Version, has_local: bool) -> list[VersionRange]:
    """Ranges for the standard PEP 440 operators (no wildcard, no ===).

    *has_local* indicates whether the spec string included a ``+local``
    segment; relevant only for ``==`` / ``!=`` to decide whether the
    upper bound includes V's local family.
    """
    if op == ">=":
        return [(_LowerBound(version, True), _POS_INF)]

    if op == "<=":
        return [
            (
                _NEG_INF,
                _UpperBound(
                    _BoundaryVersion(version, _BoundaryKind.AFTER_LOCALS), True
                ),
            )
        ]

    if op == ">":
        if version.dev is not None:
            # >V.devN: dev versions have no post-releases, so the
            # next real version is V.dev(N+1).
            lower_bound = version.__replace__(dev=version.dev + 1, local=None)
            return [(_LowerBound(lower_bound, True), _POS_INF)]
        if version.post is not None:
            # >V.postN: next real version is V.post(N+1).dev0.
            lower_bound = version.__replace__(post=version.post + 1, dev=0, local=None)
            return [(_LowerBound(lower_bound, True), _POS_INF)]
        # >V (final or pre-release V): exclude V itself, V+local, and
        # every V.postN per PEP 440.
        return [
            (
                _LowerBound(
                    _BoundaryVersion(version, _BoundaryKind.AFTER_POSTS), False
                ),
                _POS_INF,
            )
        ]

    if op == "<":
        # <V excludes pre-releases of V when V is not a pre-release.
        # V.dev0 is the earliest pre-release of V.
        bound = (
            version if version.is_prerelease else version.__replace__(dev=0, local=None)
        )
        if bound <= _MIN_VERSION:
            return []
        return [(_NEG_INF, _UpperBound(bound, False))]

    # ==, !=: local versions of V match when the spec has no local segment.
    after_locals = _BoundaryVersion(version, _BoundaryKind.AFTER_LOCALS)
    upper = version if has_local else after_locals

    if op == "==":
        return [(_LowerBound(version, True), _UpperBound(upper, True))]

    if op == "!=":
        return [
            (_NEG_INF, _UpperBound(version, False)),
            (_LowerBound(upper, False), _POS_INF),
        ]

    if op == "~=":
        prefix = version.__replace__(release=version.release[:-1])
        return [
            (_LowerBound(version, True), _UpperBound(_next_prefix_dev0(prefix), False))
        ]

    raise ValueError(f"Unknown operator: {op!r}")  # pragma: no cover
