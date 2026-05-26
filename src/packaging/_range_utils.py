# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.
"""Private interval and bounds internals shared by :mod:`packaging.ranges`
and :mod:`packaging.specifiers`.

``specifiers`` uses these directly on the filter and contains hot paths,
where routing through :meth:`VersionRange.filter` would cost measurable
performance. Everything else goes through the public
:class:`~packaging.ranges.VersionRange` API.
"""

from __future__ import annotations

import enum
import functools
from typing import (
    TYPE_CHECKING,
    Any,
    Final,
    Union,
)

from ._version_utils import coerce_version, trim_release
from .version import Version

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator, Sequence


__all__ = [
    "FULL_RANGE",
    "NEG_INF",
    "POS_INF",
    "BoundaryKind",
    "BoundaryVersion",
    "Interval",
    "LowerBound",
    "UpperBound",
    "bound_match_string",
    "bounds_for_spec",
    "filter_by_ranges",
    "intersect_ranges",
    "matches_bounds_only",
    "range_is_empty",
    "standard_ranges",
    "wildcard_ranges",
]


def __dir__() -> list[str]:
    return __all__


#: The smallest possible PEP 440 version. No valid version is less than this.
_MIN_VERSION: Final[Version] = Version("0.dev0")

#: Sorts above any real post number or local label in an ordering key.
_BOUNDARY_INF: Final[float] = float("inf")

_BoundaryOrderSuffix = tuple[int, int, int, Union[int, float], int, int]
_BoundaryOrderKey = tuple[int, tuple[int, ...], _BoundaryOrderSuffix, float]


def _next_prefix_dev0(version: Version) -> Version:
    """Smallest version in the next prefix: ``1.2 -> 1.3.dev0``."""
    release = (*version.release[:-1], version.release[-1] + 1)
    return Version.from_parts(epoch=version.epoch, release=release, dev=0)


def _base_dev0(version: Version) -> Version:
    """The ``.dev0`` of a version's base release: ``1.2 -> 1.2.dev0``."""
    return Version.from_parts(epoch=version.epoch, release=version.release, dev=0)


class BoundaryKind(enum.Enum):
    """Where a boundary marker sits in the version ordering."""

    AFTER_LOCALS = enum.auto()  # after V+local, before V.post0
    AFTER_POSTS = enum.auto()  # after V.postN, before next release


@functools.total_ordering
class BoundaryVersion:
    """A synthetic point between two real PEP 440 versions.

    PEP 440 specifier semantics imply boundaries between real versions
    (``<=1.0`` includes ``1.0+local``; ``>1.0`` excludes ``1.0.post0``).
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
        "_order_key",
        "kind",
        "version",
    )

    _order_key: _BoundaryOrderKey

    def __init__(self, version: Version, kind: BoundaryKind) -> None:
        self.version = version
        self.kind = kind
        self._cached_trimmed_release = trim_release(version.release)
        self._cached_epoch = version.epoch
        self._cached_pre = version.pre
        self._cached_post = version.post
        self._cached_dev = version.dev

        # Order key for boundary-vs-boundary comparison. Raw versions
        # are wrong (1.0.post0 > 1.0, yet AFTER_LOCALS(1.0.post0) <
        # AFTER_POSTS(1.0)); AFTER_POSTS lifts the post above any real
        # post, and both lift the local dimension.
        epoch = version._key[0]
        release = version._key[1]
        suffix: _BoundaryOrderSuffix = version._key[2]
        if kind == BoundaryKind.AFTER_POSTS:
            suffix = (suffix[0], suffix[1], 1, _BOUNDARY_INF, 1, 0)
        self._order_key = (epoch, release, suffix, _BOUNDARY_INF)

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
        if self.kind == BoundaryKind.AFTER_LOCALS:
            # Local family: same public version, any local label.
            return other.post == self._cached_post and other.dev == self._cached_dev
        # Post family: V itself + any post-release of V.
        return other.dev == self._cached_dev or other.post is not None

    def __eq__(self, other: object) -> bool:
        if isinstance(other, BoundaryVersion):
            return self.version == other.version and self.kind == other.kind
        return NotImplemented

    def __lt__(self, other: BoundaryVersion | Version) -> bool:
        if isinstance(other, BoundaryVersion):
            return self._order_key < other._order_key
        # boundary < other_version iff V < other AND other not in family.
        # The cheap V >= other path short-circuits before the family check.
        if not (self.version < other):
            return False
        return not self._is_family(other)

    def __gt__(self, other: BoundaryVersion | Version) -> bool:
        # Defined directly to bypass functools.total_ordering's
        # NotImplemented round-trip on reflected ``Version < boundary``.
        if isinstance(other, BoundaryVersion):
            return self._order_key > other._order_key
        if self.version >= other:
            return True
        return self._is_family(other)

    def __hash__(self) -> int:
        return hash((self.version, self.kind))

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.version!r}, {self.kind.name})"


if TYPE_CHECKING:
    _VersionOrBoundary = Union[Version, BoundaryVersion, None]


def _make_above_after_posts(version: Version) -> Callable[[Version], bool]:
    """Predicate ``parsed > AFTER_POSTS(v)`` for a lower bound.

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
        # parsed > v cmpkey-wise: above the boundary iff NOT in v's
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
        # In post family iff: same dev as v (covers v itself + v+local),
        # or any post-release (covers v.postN + v.postN+local).
        if parsed.dev == version_dev or parsed.post is not None:
            return False
        # Different dev with no post means parsed sorts before v
        # cmpkey-wise, in which case version_ge returned True already.
        return False  # pragma: no cover

    return above


def _make_above_after_locals(version: Version) -> Callable[[Version], bool]:
    """Predicate ``parsed > AFTER_LOCALS(v)`` for a lower bound.

    Used by the upper-side range of ``!=v`` (when *v* has no local
    segment). AFTER_LOCALS sits above v and every ``v+local`` but
    just below ``v.post0``.
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
        # parsed > v cmpkey-wise: above the boundary iff NOT in v's
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
    """Predicate ``parsed <= AFTER_LOCALS(v)`` for an upper bound.

    Used by ``<=v``, ``==v``, ``!=v`` (no local). ``parsed`` is at or
    below the boundary when it is at or below v cmpkey-wise, or when
    it is in v's local family.
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
        # parsed > v cmpkey-wise: below the boundary iff in v's local
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


def _make_below_after_posts(version: Version) -> Callable[[Version], bool]:
    """Predicate ``parsed <= AFTER_POSTS(v)`` for an upper bound.

    Mirror of :func:`_make_above_after_posts`. Produced only by
    :meth:`VersionRange.complement` of a range whose lower bound is
    AFTER_POSTS(v). ``parsed`` is at or below the boundary when it is
    at or below v cmpkey-wise, or when it is in v's post family.
    """
    version_ge = version.__ge__
    version_epoch = version.epoch
    version_pre = version.pre
    version_dev = version.dev
    version_release_trimmed = trim_release(version.release)
    trimmed_length = len(version_release_trimmed)

    def below(parsed: Version) -> bool:
        if version_ge(parsed):
            return True
        # parsed > v cmpkey-wise: below the boundary iff in v's post family.
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
        # Same dev as v with no post means parsed sorts <= v already
        # (handled by version_ge above); reach here only with parsed.post set.
        return parsed.dev == version_dev or parsed.post is not None

    return below


@functools.total_ordering
class LowerBound:
    """Lower bound of a version range.

    A ``version`` of ``None`` is unbounded below (-inf). At equal
    versions, ``[v`` sorts before ``(v`` (inclusive starts earlier).
    """

    __slots__ = ("above", "inclusive", "version")

    def __init__(self, version: _VersionOrBoundary, inclusive: bool) -> None:
        self.version = version
        self.inclusive = inclusive
        # Pre-bind a predicate "is parsed at or above this lower
        # bound?" for the hot filter / contains loops. One direct
        # call per check, no operator-dispatch chain.
        if version is None:
            self.above: Callable[[Version], bool] | None = None
        elif isinstance(version, BoundaryVersion):
            # >v produces an AFTER_POSTS lower bound; the upper-side
            # range of !=v produces an AFTER_LOCALS lower bound.
            if version.kind == BoundaryKind.AFTER_POSTS:
                self.above = _make_above_after_posts(version.version)
            else:
                self.above = _make_above_after_locals(version.version)
        elif inclusive:
            self.above = version.__le__
        else:
            self.above = version.__lt__

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, LowerBound):
            return NotImplemented  # pragma: no cover
        return self.version == other.version and self.inclusive == other.inclusive

    def __lt__(self, other: LowerBound) -> bool:
        if not isinstance(other, LowerBound):  # pragma: no cover
            return NotImplemented
        # -inf < anything (except -inf itself).
        if self.version is None:
            return other.version is not None
        if other.version is None:
            return False
        if self.version != other.version:
            return self.version < other.version
        # ``[v < (v``: inclusive starts earlier.
        return self.inclusive and not other.inclusive

    def __hash__(self) -> int:
        return hash((self.version, self.inclusive))

    def __repr__(self) -> str:
        bracket = "[" if self.inclusive else "("
        return f"<{self.__class__.__name__} {bracket}{self.version!r}>"


@functools.total_ordering
class UpperBound:
    """Upper bound of a version range.

    A ``version`` of ``None`` is unbounded above (+inf). At equal
    versions, ``v)`` sorts before ``v]`` (exclusive ends earlier).
    """

    __slots__ = ("below", "inclusive", "version")

    def __init__(self, version: _VersionOrBoundary, inclusive: bool) -> None:
        self.version = version
        self.inclusive = inclusive
        # Pre-bind a predicate "is parsed at or below this upper
        # bound?". See LowerBound for the rationale.
        if version is None:
            self.below: Callable[[Version], bool] | None = None
        elif isinstance(version, BoundaryVersion):
            # Standard specifiers only ever produce AFTER_LOCALS upper
            # bounds (from <=v / ==v / !=v with no local). Complement
            # reverses bound roles, so a range whose lower bound is
            # AFTER_POSTS(v) becomes an upper bound after complementing.
            if version.kind == BoundaryKind.AFTER_LOCALS:
                self.below = _make_below_after_locals(version.version)
            else:
                self.below = _make_below_after_posts(version.version)
        elif inclusive:
            self.below = version.__ge__
        else:
            self.below = version.__gt__

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, UpperBound):
            return NotImplemented  # pragma: no cover
        return self.version == other.version and self.inclusive == other.inclusive

    def __lt__(self, other: UpperBound) -> bool:
        if not isinstance(other, UpperBound):  # pragma: no cover
            return NotImplemented
        # Nothing < +inf (except +inf itself).
        if self.version is None:
            return False
        if other.version is None:
            return True
        if self.version != other.version:
            return self.version < other.version
        # ``v) < v]``: exclusive ends earlier.
        return not self.inclusive and other.inclusive

    def __hash__(self) -> int:
        return hash((self.version, self.inclusive))

    def __repr__(self) -> str:
        bracket = "]" if self.inclusive else ")"
        return f"<{self.__class__.__name__} {self.version!r}{bracket}>"


if TYPE_CHECKING:
    #: A single contiguous version range, as a (lower, upper) pair.
    Interval = tuple[LowerBound, UpperBound]


NEG_INF = LowerBound(None, inclusive=False)
POS_INF = UpperBound(None, inclusive=False)
FULL_RANGE: tuple[Interval] = ((NEG_INF, POS_INF),)


def range_is_empty(lower: LowerBound, upper: UpperBound) -> bool:
    """True when the range ``(lower, upper)`` contains no versions."""
    if lower.version is None or upper.version is None:
        return False
    if lower.version == upper.version:
        return not (lower.inclusive and upper.inclusive)
    return lower.version > upper.version


def intersect_ranges(
    left: Sequence[Interval],
    right: Sequence[Interval],
) -> list[Interval]:
    """Intersect two sorted, non-overlapping range lists (two-pointer merge)."""
    result: list[Interval] = []
    left_index = right_index = 0
    while left_index < len(left) and right_index < len(right):
        left_lower, left_upper = left[left_index]
        right_lower, right_upper = right[right_index]

        lower = max(left_lower, right_lower)
        upper = min(left_upper, right_upper)

        if not range_is_empty(lower, upper):
            result.append((lower, upper))

        # Advance whichever side has the smaller upper bound.
        if left_upper < right_upper:
            left_index += 1
        else:
            right_index += 1

    return result


def filter_by_ranges(
    ranges: Sequence[Interval],
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
        nonfinal_buffer: list[Any] = []
        found_final = False

        if len(ranges) == 1:
            lower, upper = ranges[0]
            above = lower.above
            below = upper.below
            for item in iterable:
                parsed = coerce_version(item if key is None else key(item))
                if parsed is None:
                    continue
                if above is not None and not above(parsed):
                    continue
                if below is not None and not below(parsed):
                    continue
                if parsed.is_prerelease:
                    if not found_final:
                        nonfinal_buffer.append(item)
                else:
                    found_final = True
                    yield item
            if not found_final:
                yield from nonfinal_buffer
            return

        for item in iterable:
            parsed = coerce_version(item if key is None else key(item))
            if parsed is None:
                continue
            for lower, upper in ranges:
                above = lower.above
                if above is not None and not above(parsed):
                    break
                below = upper.below
                if below is None or below(parsed):
                    if parsed.is_prerelease:
                        if not found_final:
                            nonfinal_buffer.append(item)
                    else:
                        found_final = True
                        yield item
                    break
        if not found_final:
            yield from nonfinal_buffer
        return

    exclude_prereleases = prereleases is False

    if len(ranges) == 1:
        # Hot path: most specifiers and small SpecifierSets reduce to
        # a single contiguous range.
        lower, upper = ranges[0]
        above = lower.above
        below = upper.below
        for item in iterable:
            parsed = coerce_version(item if key is None else key(item))
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
        parsed = coerce_version(item if key is None else key(item))
        if parsed is None:
            continue
        if exclude_prereleases and parsed.is_prerelease:
            continue
        for lower, upper in ranges:
            above = lower.above
            if above is not None and not above(parsed):
                break
            below = upper.below
            if below is None or below(parsed):
                yield item
                break


def matches_bounds_only(
    bounds: Sequence[Interval],
    item: Version,
) -> bool:
    """Pure-bounds membership check for a parsed :class:`Version`."""
    if not bounds:
        return False
    if len(bounds) == 1:
        lower, upper = bounds[0]
        above = lower.above
        if above is not None and not above(item):
            return False
        below = upper.below
        return below is None or below(item)
    for lower, upper in bounds:
        above = lower.above
        if above is not None and not above(item):
            return False
        below = upper.below
        if below is None or below(item):
            return True
    return False


def bound_match_string(bounds: Sequence[Interval], s: str) -> bool:
    """Bound-only check for the case-folded string *s*.

    Full-range bounds admit any string. Other shapes require *s* to
    parse and fall inside the intervals.
    """
    if tuple(bounds) == FULL_RANGE:
        return True
    parsed = coerce_version(s)
    if parsed is None:
        return False
    return matches_bounds_only(bounds, parsed)


def wildcard_ranges(op: str, base: Version) -> tuple[Interval, ...]:
    """Ranges for ``==V.*`` and ``!=V.*``.

    ``==1.2.*`` -> ``[1.2.dev0, 1.3.dev0)``;  ``!=1.2.*`` -> complement.
    """
    lower = _base_dev0(base)
    upper = _next_prefix_dev0(base)
    if op == "==":
        return (
            (LowerBound(lower, inclusive=True), UpperBound(upper, inclusive=False)),
        )
    # !=
    return (
        (NEG_INF, UpperBound(lower, inclusive=False)),
        (LowerBound(upper, inclusive=True), POS_INF),
    )


def standard_ranges(
    operator: str, version: Version, has_local: bool
) -> tuple[Interval, ...]:
    """Ranges for the standard PEP 440 operators (no wildcard, no ===).

    *has_local* indicates whether the spec string included a ``+local``
    segment; relevant only for ``==`` / ``!=`` to decide whether the
    upper bound includes V's local family.
    """
    if operator == ">=":
        return ((LowerBound(version, inclusive=True), POS_INF),)

    if operator == "<=":
        return (
            (
                NEG_INF,
                UpperBound(
                    BoundaryVersion(version, BoundaryKind.AFTER_LOCALS), inclusive=True
                ),
            ),
        )

    if operator == ">":
        if version.dev is not None:
            # >V.devN: dev versions have no post-releases, so the
            # next real version is V.dev(N+1).
            lower_bound = version.__replace__(dev=version.dev + 1, local=None)
            return ((LowerBound(lower_bound, inclusive=True), POS_INF),)
        if version.post is not None:
            # >V.postN: next real version is V.post(N+1).dev0.
            lower_bound = version.__replace__(post=version.post + 1, dev=0, local=None)
            return ((LowerBound(lower_bound, inclusive=True), POS_INF),)
        # >V (final or pre-release V): exclude V itself, V+local, and
        # every V.postN per PEP 440.
        return (
            (
                LowerBound(
                    BoundaryVersion(version, BoundaryKind.AFTER_POSTS), inclusive=False
                ),
                POS_INF,
            ),
        )

    if operator == "<":
        # <V excludes pre-releases of V when V is not a pre-release.
        # V.dev0 is the earliest pre-release of V.
        bound = (
            version if version.is_prerelease else version.__replace__(dev=0, local=None)
        )
        if bound <= _MIN_VERSION:
            return ()
        return ((NEG_INF, UpperBound(bound, inclusive=False)),)

    # ==, !=: local versions of V match when the spec has no local segment.
    after_locals = BoundaryVersion(version, BoundaryKind.AFTER_LOCALS)
    upper = version if has_local else after_locals

    if operator == "==":
        return (
            (LowerBound(version, inclusive=True), UpperBound(upper, inclusive=True)),
        )

    if operator == "!=":
        return (
            (NEG_INF, UpperBound(version, inclusive=False)),
            (LowerBound(upper, inclusive=False), POS_INF),
        )

    if operator == "~=":
        prefix = version.__replace__(release=version.release[:-1])
        return (
            (
                LowerBound(version, inclusive=True),
                UpperBound(_next_prefix_dev0(prefix), inclusive=False),
            ),
        )

    raise ValueError(f"Unknown operator: {operator!r}")  # pragma: no cover


def bounds_for_spec(operator: str, version_str: str) -> tuple[Interval, ...]:
    """Return the bound intervals for one ``(operator, version_string)``.

    Must not be called with ``operator == "==="``; that operator carries
    a literal string match handled at the :class:`VersionRange` layer instead.
    """
    if version_str.endswith(".*"):
        base = coerce_version(version_str[:-2])
        assert base is not None  # the specifier regex guarantees a valid base
        return wildcard_ranges(operator, base)

    version = coerce_version(version_str)
    assert version is not None  # the specifier regex guarantees a valid version

    return standard_ranges(
        operator=operator, version=version, has_local="+" in version_str
    )
