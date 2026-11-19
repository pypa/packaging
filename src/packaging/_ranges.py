# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.
"""Private version-range helpers used by :mod:`packaging.specifiers`."""

from __future__ import annotations

__lazy_modules__ = {"bisect"}

import enum
import functools
from bisect import bisect_right
from typing import (
    TYPE_CHECKING,
    Any,
    Final,
)

from .version import InvalidVersion, Version

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator, Sequence

    # Total-order key for comparing two boundaries (boundary-vs-boundary only).
    # The post slot may be ``_BOUNDARY_INF`` for an AFTER_POSTS boundary.
    _BoundaryOrderSuffix = tuple[int, int, int, int | float, int, int]
    _BoundaryOrderKey = tuple[int, tuple[int, ...], _BoundaryOrderSuffix, float]

__all__ = [
    "FULL_RANGE",
    "bounds_for_spec",
    "coerce_version",
    "filter_by_ranges",
    "first_version_after_locals",
    "intersect_ranges",
    "intersect_specifier_bounds",
    "matches_bounds_only",
    "range_is_empty",
    "ranges_are_disjoint",
    "ranges_are_prerelease_only",
    "resolve_prereleases",
    "standard_ranges",
    "wildcard_ranges",
]

#: The smallest possible PEP 440 version. No valid version is less than this.
MIN_VERSION: Final[Version] = Version("0.dev0")

#: The smallest non-pre-release version, i.e. the nearest non-pre-release at or
#: above the ``-inf`` floor.
MIN_RELEASE: Final[Version] = Version("0")

#: Sorts above any real post number and any local label, so a boundary can be
#: ordered above the version family it covers when two boundaries are compared.
_BOUNDARY_INF: Final[float] = float("inf")

#: Edge keys compare against ``Version._key`` with plain tuple ordering: a
#: version is inside ``(lower, upper)`` iff
#: ``lower._floor_key <= version._key < upper._ceiling_key``. An empty key is
#: an unbounded side, and this marks a bound that no single key expresses.
_NO_EDGE_KEY: Final[tuple[Any, ...]] = (None,)

#: A local segment that sorts above every real one.
_LOCAL_KEY_MAX: Final[tuple[Any, ...]] = ((_BOUNDARY_INF,),)


class BoundaryKind(enum.Enum):
    """Where a boundary marker sits in the version ordering."""

    AFTER_LOCALS = enum.auto()  # after V+local, before V.post0
    AFTER_POSTS = enum.auto()  # after V.postN, before next release


@functools.total_ordering
class BoundaryVersion:
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
        "_cached_successor",
        "_cached_trimmed_release",
        "kind",
        "version",
    )

    # Synthetic boundaries must use version operators rather than cached keys.
    _key_cache: None = None

    def __init__(self, version: Version, kind: BoundaryKind) -> None:
        self.version = version
        self.kind = kind
        self._cached_trimmed_release = trim_release(version.release)
        self._cached_epoch = version.epoch
        self._cached_pre = version.pre
        self._cached_post = version.post
        self._cached_dev = version.dev
        self._cached_successor: Version | None = None

    @property
    def successor(self) -> Version | None:
        """The smallest real version above this boundary, if one exists."""
        if self._cached_successor is not None:
            return self._cached_successor

        if self.kind is BoundaryKind.AFTER_LOCALS:
            self._cached_successor = first_version_after_locals(self.version)
        elif self.version.pre is not None:
            # The first version after 1a1 and all its post-releases is 1a2.dev0.
            tag, number = self.version.pre
            self._cached_successor = self.version.__replace__(
                pre=(tag, number + 1), post=None, dev=0, local=None
            )

        return self._cached_successor

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

    def _order_key(self) -> _BoundaryOrderKey:
        """Sort key placing this boundary just above the versions it covers.

        It extends ``V``'s comparison key ``(epoch, release, suffix)`` with
        a trailing ``_BOUNDARY_INF`` local component, so the key sorts after
        ``V`` and every ``V+local`` (whose keys carry a real, finite local
        segment). ``suffix`` is the 6-int comparison suffix
        ``(pre_rank, pre_n, post_rank, post_n, dev_rank, dev_n)``.

        For an AFTER_POSTS boundary the suffix is replaced with one whose
        post number is ``_BOUNDARY_INF``, so the key also sorts after every
        ``V.postN``. An AFTER_LOCALS boundary uses ``V``'s suffix unchanged.
        """
        version_key = self.version._key
        suffix: _BoundaryOrderSuffix = version_key[2]

        if self.kind == BoundaryKind.AFTER_POSTS:
            suffix = (suffix[0], suffix[1], 1, _BOUNDARY_INF, 1, 0)

        return version_key[0], version_key[1], suffix, _BOUNDARY_INF

    def __eq__(self, other: object) -> bool:
        # Key off the order key so equality matches the ``<`` / ``>`` order:
        # ``AFTER_POSTS(1.0)`` and ``AFTER_POSTS(1.0.post1)`` are the same point.
        if isinstance(other, BoundaryVersion):
            return self._order_key() == other._order_key()
        return NotImplemented

    def __lt__(self, other: BoundaryVersion | Version) -> bool:
        if isinstance(other, BoundaryVersion):
            return self._order_key() < other._order_key()
        # boundary < other_version iff V < other AND other not in family.
        # The cheap V >= other path short-circuits before the family check.
        if not (self.version < other):
            return False
        return not self._is_family(other)

    def __gt__(self, other: BoundaryVersion | Version) -> bool:
        # Defined directly to bypass functools.total_ordering's
        # NotImplemented round-trip on reflected ``Version < boundary``.
        if isinstance(other, BoundaryVersion):
            return self._order_key() > other._order_key()
        if self.version >= other:
            return True
        return self._is_family(other)

    def __hash__(self) -> int:
        # Keyed to ``__eq__`` (the order key), so equal boundaries hash equal.
        return hash(self._order_key())

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.version!r}, {self.kind.name})"


if TYPE_CHECKING:
    _VersionOrBoundary = Version | BoundaryVersion | None


@functools.total_ordering
class LowerBound:
    """Lower bound of a version range.

    A version *v* of ``None`` means unbounded below (-inf), with
    ``inclusive`` forced to ``False``.
    At equal versions, ``[v`` sorts before ``(v`` because an inclusive
    bound starts earlier.
    """

    __slots__ = ("_above", "_floor_key", "inclusive", "version")

    def __init__(self, version: _VersionOrBoundary, inclusive: bool) -> None:
        # Two spellings of -inf would sort above each other under total_ordering.
        if version is None:
            inclusive = False

        self.version = version
        self.inclusive = inclusive
        # Filled by ``_edge_keys`` on first use, to keep construction cheap.
        self._floor_key: tuple[Any, ...] | None = None
        # Pre-bind a predicate "is parsed at or above this lower
        # bound?" for the hot filter / contains loops. One direct
        # call per check, no operator-dispatch chain.
        if version is None:
            self._above: Callable[[Version], bool] | None = None
        elif isinstance(version, BoundaryVersion):
            # >V produces an AFTER_POSTS lower bound; the upper-side
            # range of !=V produces an AFTER_LOCALS lower bound.
            if version.kind == BoundaryKind.AFTER_POSTS:
                self._above = _make_above_after_posts(version.version)
            else:
                self._above = _make_above_after_locals(version.version)
        elif inclusive:
            self._above = version.__le__
        else:
            self._above = version.__lt__

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, LowerBound):
            return NotImplemented
        return self.version == other.version and self.inclusive == other.inclusive

    def __lt__(self, other: LowerBound) -> bool:
        if not isinstance(other, LowerBound):
            return NotImplemented
        # -inf < anything (except -inf itself).
        if self.version is None:
            return other.version is not None
        if other.version is None:
            return False

        # Use cached keys when both exist; cold versions and boundaries use operators.
        self_key = self.version._key_cache
        other_key = other.version._key_cache
        if self_key is None or other_key is None:
            if self.version != other.version:
                return self.version < other.version
        elif self_key != other_key:
            return self_key < other_key

        # [v < (v: inclusive starts earlier.
        return self.inclusive and not other.inclusive

    # Explicit operators avoid total_ordering's repeated comparison dispatch.
    def __gt__(self, other: LowerBound) -> bool:
        if not isinstance(other, LowerBound):
            return NotImplemented
        if self.version is None:
            return False
        if other.version is None:
            return True

        self_key = self.version._key_cache
        other_key = other.version._key_cache
        if self_key is None or other_key is None:
            if self.version != other.version:
                return other.version < self.version
        elif self_key != other_key:
            return other_key < self_key

        return other.inclusive and not self.inclusive

    def __le__(self, other: LowerBound) -> bool:
        if not isinstance(other, LowerBound):
            return NotImplemented
        if self.version is None:
            return True
        if other.version is None:
            return False

        self_key = self.version._key_cache
        other_key = other.version._key_cache
        if self_key is None or other_key is None:
            if self.version != other.version:
                return self.version < other.version
        elif self_key != other_key:
            return self_key < other_key

        return self.inclusive or not other.inclusive

    def __hash__(self) -> int:
        return hash((self.version, self.inclusive))

    def __repr__(self) -> str:
        bracket = "[" if self.inclusive else "("
        return f"<{self.__class__.__name__} {bracket}{self.version!r}>"


@functools.total_ordering
class UpperBound:
    """Upper bound of a version range.

    A version *v* of ``None`` means unbounded above (+inf), with
    ``inclusive`` forced to ``False``.
    At equal versions, ``v)`` sorts before ``v]`` because an exclusive
    bound ends earlier.
    """

    __slots__ = ("_below", "_ceiling_key", "inclusive", "version")

    def __init__(self, version: _VersionOrBoundary, inclusive: bool) -> None:
        # Two spellings of +inf would sort above each other under total_ordering.
        if version is None:
            inclusive = False

        self.version = version
        self.inclusive = inclusive
        self._ceiling_key: tuple[Any, ...] | None = None
        # Pre-bind a predicate "is parsed at or below this upper
        # bound?". See LowerBound for the rationale.
        if version is None:
            self._below: Callable[[Version], bool] | None = None
        elif isinstance(version, BoundaryVersion):
            # Standard specifiers only ever produce AFTER_LOCALS upper
            # bounds (from <=V / ==V / !=V with no local).
            if version.kind == BoundaryKind.AFTER_LOCALS:
                self._below = _make_below_after_locals(version.version)
            else:
                # An AFTER_POSTS upper is not produced by any specifier, but
                # range algebra reaches it: complementing ``>V`` flips the
                # ``AFTER_POSTS(V)`` lower into this upper bound.
                self._below = version.__ge__
        elif inclusive:
            self._below = version.__ge__
        else:
            self._below = version.__gt__

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, UpperBound):
            return NotImplemented
        return self.version == other.version and self.inclusive == other.inclusive

    def __lt__(self, other: UpperBound) -> bool:
        if not isinstance(other, UpperBound):
            return NotImplemented
        # An unbounded upper endpoint does not sort before any endpoint.
        if self.version is None:
            return False
        if other.version is None:
            return True

        # Use cached keys when both exist; cold versions and boundaries use operators.
        self_key = self.version._key_cache
        other_key = other.version._key_cache
        if self_key is None or other_key is None:
            if self.version != other.version:
                return self.version < other.version
        elif self_key != other_key:
            return self_key < other_key

        # v) < v]: exclusive ends earlier.
        return not self.inclusive and other.inclusive

    def __gt__(self, other: UpperBound) -> bool:
        if not isinstance(other, UpperBound):
            return NotImplemented
        if self.version is None:
            return other.version is not None
        if other.version is None:
            return False

        self_key = self.version._key_cache
        other_key = other.version._key_cache
        if self_key is None or other_key is None:
            if self.version != other.version:
                return other.version < self.version
        elif self_key != other_key:
            return other_key < self_key

        return self.inclusive and not other.inclusive

    def __hash__(self) -> int:
        return hash((self.version, self.inclusive))

    def __repr__(self) -> str:
        bracket = "]" if self.inclusive else ")"
        return f"<{self.__class__.__name__} {self.version!r}{bracket}>"


if TYPE_CHECKING:
    #: A single contiguous interval as a (lower, upper) bound pair.
    Interval = tuple[LowerBound, UpperBound]


NEG_INF: Final[LowerBound] = LowerBound(None, False)
POS_INF: Final[UpperBound] = UpperBound(None, False)
FULL_RANGE: Final[tuple[Interval]] = ((NEG_INF, POS_INF),)


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


def coerce_version(version: Version | str) -> Version | None:
    if not isinstance(version, Version):
        try:
            version = Version(version)
        except InvalidVersion:
            return None
    return version


def _successor_key(key: tuple[Any, ...]) -> tuple[Any, ...]:
    """Smallest edge key above a version key: every greater version key is above it.

    An empty local segment sorts below every real one, so appending it gives
    the next point after a key with or without a local label.
    """
    return (*key[:3], (*key[3], ())) if len(key) == 4 else (*key, ())


def _boundary_key(boundary: BoundaryVersion) -> tuple[Any, ...]:
    """Edge key for the point where *boundary* sits."""
    version = boundary.version
    epoch, release, suffix = version._key[:3]
    if boundary.kind == BoundaryKind.AFTER_LOCALS:
        return epoch, release, suffix, _LOCAL_KEY_MAX
    if version._pre is not None:
        # Above every post-release of this pre-release, below the next one.
        return epoch, release, (suffix[0], suffix[1], _BOUNDARY_INF)
    if version._dev is not None and version._post is None:
        # The family of a dev-only release is not contiguous in key order.
        return _NO_EDGE_KEY
    return epoch, release, (_BOUNDARY_INF,)


def _edge_keys(
    lower: LowerBound, upper: UpperBound
) -> tuple[tuple[Any, ...], tuple[Any, ...]]:
    """Compute and cache the ``(floor_key, ceiling_key)`` of an interval."""
    floor_key = lower._floor_key
    if floor_key is None:
        version = lower.version
        if version is None:
            floor_key = ()
        elif isinstance(version, BoundaryVersion):
            floor_key = _boundary_key(version)
        elif lower.inclusive:
            floor_key = version._key
        else:
            floor_key = _successor_key(version._key)
        lower._floor_key = floor_key

    ceiling_key = upper._ceiling_key
    if ceiling_key is None:
        version = upper.version
        if version is None:
            ceiling_key = ()
        elif isinstance(version, BoundaryVersion):
            # ``_below`` of an AFTER_POSTS upper does not mirror ``_above``.
            if version.kind == BoundaryKind.AFTER_LOCALS:
                ceiling_key = _boundary_key(version)
            else:
                ceiling_key = _NO_EDGE_KEY
        elif upper.inclusive:
            ceiling_key = _successor_key(version._key)
        else:
            ceiling_key = version._key
        upper._ceiling_key = ceiling_key

    return floor_key, ceiling_key


def _flat_edge_keys(ranges: Sequence[Interval]) -> list[tuple[Any, ...]] | None:
    """Edge keys of sorted *ranges* in one ascending list, for bisection.

    A version is inside the ranges iff an odd number of edges are at or below
    its key. Returns ``None`` when a bound has no edge key.
    """
    edges: list[tuple[Any, ...]] = []
    for lower, upper in ranges:
        floor_key = lower._floor_key
        ceiling_key = upper._ceiling_key
        if floor_key is None or ceiling_key is None:
            floor_key, ceiling_key = _edge_keys(lower, upper)
        if floor_key is _NO_EDGE_KEY or ceiling_key is _NO_EDGE_KEY:
            return None
        edges.append(floor_key)
        # Only the last range can be unbounded above; it adds no closing edge.
        if ceiling_key:
            edges.append(ceiling_key)
    return edges


def _make_above_after_posts(version: Version) -> Callable[[Version], bool]:
    """Predicate ``parsed > AFTER_POSTS(V)`` for a lower bound.

    Per PEP 440, ``>V`` excludes V's post-releases unless V is itself
    a post-release. AFTER_POSTS sits above V and every V.postN (with
    or without local), and just below the next release.
    """
    version_key = version._key
    version_pre = version._pre

    def above(parsed: Version) -> bool:
        # Above V by key, and not in V's post family: the later versions
        # that share V's epoch, trimmed release (the first two key items),
        # and pre segment.
        key = parsed._key_cache or parsed._key
        return key > version_key and (
            key[0] != version_key[0]
            or key[1] != version_key[1]
            or parsed._pre != version_pre
        )

    return above


def _make_above_after_locals(version: Version) -> Callable[[Version], bool]:
    """Match above a public version and all of its local labels."""
    # The first three key fields identify the complete public version.
    version_key = version._key[:3]

    def above(parsed: Version) -> bool:
        key = parsed._key_cache or parsed._key
        return key[:3] > version_key

    return above


def _make_below_after_locals(version: Version) -> Callable[[Version], bool]:
    """Match at or below the public version encoded by the first three key fields."""
    version_key = version._key[:3]

    def below(parsed: Version) -> bool:
        key = parsed._key_cache or parsed._key
        return key[:3] <= version_key

    return below


def first_version_after_locals(version: Version) -> Version:
    """The first version above *version* and all its local versions."""
    if version.dev is not None:
        return version.__replace__(dev=version.dev + 1, local=None)

    next_post = version.post + 1 if version.post is not None else 0
    return version.__replace__(post=next_post, dev=0, local=None)


def range_is_empty(lower: LowerBound, upper: UpperBound) -> bool:
    """True when the range defined by *lower* and *upper* contains no versions.

    A boundary lower sits just below the next real version, so an ordered pair
    is still empty when the upper excludes that least successor:
    ``(AFTER_POSTS(1.0a1), 1.0a2.dev0)`` holds no version.
    """
    upper_version = upper.version
    if upper_version is None:
        return False

    lower_version = lower.version
    if lower_version is None:
        # Nothing sorts below MIN_VERSION, so an exclusive upper at or below it
        # leaves an empty floor interval such as ``(-inf, 0.dev0)``.
        return (
            not upper.inclusive
            and isinstance(upper_version, Version)
            and upper_version <= MIN_VERSION
        )

    lower_key = lower_version._key_cache
    upper_key = upper_version._key_cache
    if lower_key is not None and upper_key is not None:
        if lower.inclusive and upper.inclusive:
            return lower_key > upper_key
        return lower_key >= upper_key

    if isinstance(lower_version, BoundaryVersion):
        successor = lower_version.successor
        if successor is not None:
            if upper_version == successor:
                return not upper.inclusive
            return upper_version < successor

    if lower_version == upper_version:
        return not (lower.inclusive and upper.inclusive)

    return lower_version > upper_version


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


def ranges_are_disjoint(left: Sequence[Interval], right: Sequence[Interval]) -> bool:
    """Test whether two sorted, non-overlapping interval lists are disjoint.

    Each interval must contain at least one version; empty input lists are allowed.
    """
    left_index = right_index = 0
    while left_index < len(left) and right_index < len(right):
        left_lower, left_upper = left[left_index]
        right_lower, right_upper = right[right_index]

        if range_is_empty(left_lower, right_upper):
            right_index += 1
        elif range_is_empty(right_lower, left_upper):
            left_index += 1
        else:
            return False

    return True


def filter_by_ranges(
    ranges: Sequence[Interval],
    iterable: Iterable[Any],
    key: Callable[[Any], Version | str] | None,
    prereleases: bool | None,
    region: Sequence[Interval] = (),
) -> Iterator[Any]:
    """Filter *iterable* against precomputed version *ranges*.

    With ``prereleases=None``, the PEP 440 default applies: pre-releases are
    excluded unless no final matches, in which case buffered pre-releases come
    out at the end. A pre-release inside the opt-in ``region`` is the exception:
    it is force-admitted in place, as ``prereleases=True`` would yield it. A
    force-admitted pre-release is not a final, so it never suppresses the buffer.
    """
    # Hot path: most specifiers and small SpecifierSets reduce to a single
    # contiguous range, tested by comparing version keys inline.
    keyed = False
    edges = None
    if len(ranges) == 1:
        lower, upper = ranges[0]
        floor_key = lower._floor_key
        ceiling_key = upper._ceiling_key
        if floor_key is None or ceiling_key is None:
            floor_key, ceiling_key = _edge_keys(lower, upper)
        keyed = floor_key is not _NO_EDGE_KEY and ceiling_key is not _NO_EDGE_KEY
        # None is the cheapest unbounded test inside the loops.
        floor_key = floor_key or None
        ceiling_key = ceiling_key or None
    else:
        edges = _flat_edge_keys(ranges)

    if prereleases is None:
        prerelease_buffer: list[Any] = []
        found_final = False

        if keyed:
            for item in iterable:
                parsed = item if key is None else key(item)
                if not isinstance(parsed, Version):
                    parsed = coerce_version(parsed)
                    if parsed is None:
                        continue
                version_key = parsed._key_cache or parsed._key
                if floor_key is not None and version_key < floor_key:
                    continue
                if ceiling_key is not None and version_key >= ceiling_key:
                    continue
                if not parsed.is_prerelease:
                    found_final = True
                    yield item
                elif region and matches_bounds_only(region, parsed):
                    yield item
                elif not found_final:
                    prerelease_buffer.append(item)
            if not found_final:
                yield from prerelease_buffer
            return

        for item in iterable:
            parsed = item if key is None else key(item)
            if not isinstance(parsed, Version):
                parsed = coerce_version(parsed)
                if parsed is None:
                    continue
            if edges is None:
                if not matches_bounds_only(ranges, parsed):
                    continue
            elif not bisect_right(edges, parsed._key_cache or parsed._key) & 1:
                continue
            if not parsed.is_prerelease:
                found_final = True
                yield item
            elif region and matches_bounds_only(region, parsed):
                yield item
            elif not found_final:
                prerelease_buffer.append(item)
        if not found_final:
            yield from prerelease_buffer
        return

    exclude_prereleases = prereleases is False

    if keyed:
        for item in iterable:
            parsed = item if key is None else key(item)
            if not isinstance(parsed, Version):
                parsed = coerce_version(parsed)
                if parsed is None:
                    continue
            if exclude_prereleases and parsed.is_prerelease:
                continue
            version_key = parsed._key_cache or parsed._key
            if floor_key is not None and version_key < floor_key:
                continue
            if ceiling_key is None or version_key < ceiling_key:
                yield item
        return

    for item in iterable:
        parsed = item if key is None else key(item)
        if not isinstance(parsed, Version):
            parsed = coerce_version(parsed)
            if parsed is None:
                continue
        if exclude_prereleases and parsed.is_prerelease:
            continue
        if edges is None:
            if matches_bounds_only(ranges, parsed):
                yield item
        elif bisect_right(edges, parsed._key_cache or parsed._key) & 1:
            yield item


def _nearest_release_above_prerelease(version: Version) -> Version:
    """Smallest non-pre-release at or above a pre-release *version*."""
    if version.pre is not None:
        # An a/b/rc pre-release drops to its final release, which outranks
        # every post-release of that pre-release (1.0a1.post0 -> 1.0).
        return version.__replace__(pre=None, post=None, dev=None, local=None)

    # A dev-only release keeps its post-release (1.0.post0.dev0 -> 1.0.post0,
    # whose final 1.0 sorts below it).
    return version.__replace__(dev=None, local=None)


def _lowest_release_at_or_above(value: Version | BoundaryVersion | None) -> Version:
    """Smallest non-pre-release version at or above *value*.

    ``None`` is the ``-inf`` floor, whose nearest non-pre-release is
    :data:`MIN_RELEASE`.
    """
    if value is None:
        return MIN_RELEASE
    if isinstance(value, BoundaryVersion):
        inner_version = value.version
        if inner_version.is_prerelease:
            return _nearest_release_above_prerelease(inner_version)
        # AFTER_LOCALS(1.0) -> nearest non-pre is 1.0.post0
        # AFTER_LOCALS(1.0.post0) -> nearest non-pre is 1.0.post1
        next_post = (inner_version.post + 1) if inner_version.post is not None else 0
        return inner_version.__replace__(post=next_post, local=None)

    if not value.is_prerelease:
        return value

    return _nearest_release_above_prerelease(value)


def ranges_are_prerelease_only(ranges: Sequence[Interval]) -> bool:
    """True when every range in *ranges* contains only pre-releases.

    Used to detect unsatisfiable specifier sets when ``prereleases=False``:
    if every range is pre-release-only, every contained version is excluded.
    """
    for lower, upper in ranges:
        nearest = _lowest_release_at_or_above(lower.version)
        if upper.version is None or nearest < upper.version:
            return False
        if nearest == upper.version and upper.inclusive:
            return False
    return True


def wildcard_ranges(op: str, base: Version) -> list[Interval]:
    """Ranges for ==V.* and !=V.*.

    ==1.2.* -> [1.2.dev0, 1.3.dev0);  !=1.2.* -> complement.
    """
    lower = _base_dev0(base)
    upper = _next_prefix_dev0(base)
    if op == "==":
        return [(LowerBound(lower, True), UpperBound(upper, False))]
    # !=
    return [
        (NEG_INF, UpperBound(lower, False)),
        (LowerBound(upper, True), POS_INF),
    ]


def standard_ranges(op: str, version: Version, has_local: bool) -> list[Interval]:
    """Ranges for the standard PEP 440 operators (no wildcard, no ===).

    *has_local* indicates whether the spec string included a ``+local``
    segment; relevant only for ``==`` / ``!=`` to decide whether the
    upper bound includes V's local family.
    """
    if op == ">=":
        return [(LowerBound(version, True), POS_INF)]

    if op == "<=":
        return [
            (
                NEG_INF,
                UpperBound(BoundaryVersion(version, BoundaryKind.AFTER_LOCALS), True),
            )
        ]

    if op == ">":
        if version.dev is not None:
            # >V.devN: dev versions have no post-releases, so the
            # next real version is V.dev(N+1).
            lower_bound = version.__replace__(dev=version.dev + 1, local=None)
            return [(LowerBound(lower_bound, True), POS_INF)]
        if version.post is not None:
            # >V.postN: next real version is V.post(N+1).dev0.
            lower_bound = version.__replace__(post=version.post + 1, dev=0, local=None)
            return [(LowerBound(lower_bound, True), POS_INF)]
        # >V (final or pre-release V): exclude V itself, V+local, and
        # every V.postN per PEP 440.
        return [
            (
                LowerBound(BoundaryVersion(version, BoundaryKind.AFTER_POSTS), False),
                POS_INF,
            )
        ]

    if op == "<":
        # <V excludes pre-releases of V when V is not a pre-release.
        # V.dev0 is the earliest pre-release of V.
        bound = (
            version if version.is_prerelease else version.__replace__(dev=0, local=None)
        )
        if bound <= MIN_VERSION:
            return []
        return [(NEG_INF, UpperBound(bound, False))]

    if op == "~=":
        prefix = version.__replace__(release=version.release[:-1])
        return [
            (LowerBound(version, True), UpperBound(_next_prefix_dev0(prefix), False))
        ]

    # ==1.4 includes every local version of 1.4, and !=1.4 excludes them all.
    upper = (
        version if has_local else BoundaryVersion(version, BoundaryKind.AFTER_LOCALS)
    )

    if op == "==":
        return [(LowerBound(version, True), UpperBound(upper, True))]

    if op == "!=":
        return [
            (NEG_INF, UpperBound(version, False)),
            (LowerBound(upper, False), POS_INF),
        ]

    raise ValueError(f"Unknown operator: {op!r}")  # pragma: no cover


def bounds_for_spec(op: str, version_str: str, version: Version) -> list[Interval]:
    """Ranges for one specifier's ``(op, version_str)``.

    Dispatches between the wildcard and standard builders. ``version`` is the
    parsed ``version_str`` (its base, without the trailing ``.*``, for
    wildcards). ``===`` is not handled here; its match is a literal string
    compared in :mod:`packaging.specifiers`.
    """
    if version_str.endswith(".*"):
        return wildcard_ranges(op, version)

    return standard_ranges(op, version, "+" in version_str)


def intersect_specifier_bounds(
    per_specifier_ranges: Iterable[Sequence[Interval]],
) -> Sequence[Interval]:
    """Intersect each specifier's ranges into a single sequence.

    Short-circuits once the running intersection is empty, since no later
    specifier can revive it. Callers must pass at least one specifier.
    """
    result: Sequence[Interval] | None = None
    for sub in per_specifier_ranges:
        if result is None:
            result = sub
        else:
            result = intersect_ranges(result, sub)
            if not result:
                break

    if result is None:  # pragma: no cover - callers guard non-empty input
        raise RuntimeError("intersect_specifier_bounds called with no specifiers")

    return result


def matches_bounds_only(ranges: Sequence[Interval], version: Version) -> bool:
    """Whether ``version`` falls within any of ``ranges``.

    The pure bounds membership test, for a single already-parsed version with
    no pre-release policy applied. ``ranges`` are sorted and non-overlapping,
    so a version below one range's lower bound is below every later range too.
    """
    version_key = version._key_cache or version._key
    for lower, upper in ranges:
        floor_key = lower._floor_key
        ceiling_key = upper._ceiling_key
        if floor_key is None or ceiling_key is None:
            floor_key, ceiling_key = _edge_keys(lower, upper)

        if floor_key is _NO_EDGE_KEY or ceiling_key is _NO_EDGE_KEY:
            above = lower._above
            if above is not None and not above(version):
                return False
            below = upper._below
            if below is None or below(version):
                return True
        elif version_key < floor_key:
            return False
        elif not ceiling_key or version_key < ceiling_key:
            return True

    return False


def resolve_prereleases(
    configured: bool | None, autodetected: bool | None
) -> bool | None:
    """Resolve a specifier's effective default pre-release policy.

    An explicit ``configured`` value wins; otherwise an autodetected ``True``
    propagates and anything else falls back to the PEP 440 default (``None``).
    """
    if configured is not None:
        return configured

    if autodetected:
        return True

    return None
