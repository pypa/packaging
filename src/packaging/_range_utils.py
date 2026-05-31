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

from ._version_utils import coerce_version, trim_release, version_cmpkey
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
    "bounds_for_spec",
    "canonical_lower",
    "filter_by_ranges",
    "intersect_ranges",
    "intersect_specifier_bounds",
    "matches_bounds_only",
    "range_is_empty",
    "ranges_are_prerelease_only",
    "resolve_prereleases",
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
    """Where a boundary marker sits in the version ordering.

    Values are part of the cross-release pickle contract: never reuse a
    retired value, only allocate new ones. The user-facing
    :meth:`VersionRange.__repr__` renders the name for human readability,
    and :data:`packaging.ranges._KIND_TO_CODE` mirrors these values so
    renaming a member doesn't change the on-the-wire format.
    """

    AFTER_LOCALS = 1  # after V+local, before V.post0
    AFTER_POSTS = 2  # after V.postN, before next release


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
        "_cached_order_key",
        "_cached_post",
        "_cached_pre",
        "_cached_trimmed_release",
        "kind",
        "version",
    )

    _cached_order_key: _BoundaryOrderKey | None

    def __init__(self, version: Version, kind: BoundaryKind) -> None:
        # AFTER_POSTS absorbs V's post and dev into the synthetic suffix,
        # so a base V carrying either would silently equal the bare-V
        # boundary under the sort order while __eq__ still distinguished
        # them, violating functools.total_ordering. Local is forbidden
        # because version_cmpkey drops it. Standard callers only build
        # AFTER_POSTS from >V (PEP 440 forbids local on > and disallows
        # the dev/post cases at this site), so this is a caller invariant.
        if kind == BoundaryKind.AFTER_POSTS:
            assert version.post is None
            assert version.dev is None
            assert version.local is None

        # AFTER_LOCALS absorbs V's local family, and version_cmpkey discards
        # the local segment, so two AFTER_LOCALS with the same base but
        # different locals would compare equal under sort while __eq__
        # reported them unequal. Standard callers only build AFTER_LOCALS
        # from <=V, ==V, or !=V with no local segment in the spec.
        if kind == BoundaryKind.AFTER_LOCALS:
            assert version.local is None

        self.version = version
        self.kind = kind
        self._cached_trimmed_release = trim_release(version.release)
        self._cached_epoch = version.epoch
        self._cached_pre = version.pre
        self._cached_post = version.post
        self._cached_dev = version.dev
        # Lazy: only boundary-vs-boundary sort comparisons need it, and
        # those are exclusive to set algebra (union, intersection,
        # complement). Membership-only paths (Specifier.filter / contains)
        # never touch it.
        self._cached_order_key = None

    def _order_key(self) -> _BoundaryOrderKey:
        """Sort key handling cross-base AFTER_LOCALS / AFTER_POSTS pairs.

        Inline base-version comparison is insufficient when one operand
        is ``AFTER_POSTS(V)`` and the other is ``AFTER_LOCALS(V.postN)``:
        the latter sits between ``V.postN+local`` and ``V.postN+1`` while
        the former sits above every post of ``V``. Encoding the post slot
        as ``+inf`` for AFTER_POSTS makes the comparison fall out.
        """
        key = self._cached_order_key
        if key is not None:
            return key
        epoch, release, raw_suffix = version_cmpkey(self.version)
        suffix: _BoundaryOrderSuffix = raw_suffix
        if self.kind == BoundaryKind.AFTER_POSTS:
            suffix = (suffix[0], suffix[1], 1, _BOUNDARY_INF, 1, 0)
        key = (epoch, release, suffix, _BOUNDARY_INF)
        self._cached_order_key = key
        return key

    def _is_family(self, other: Version) -> bool:
        """Is ``other`` a version that this boundary sorts above?"""
        if other.epoch != self._cached_epoch:
            return False

        # Match the trimmed release without allocating a new tuple.
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

    AFTER_LOCALS sits above v and every ``v+local`` but just below
    ``v.post0``.
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

    ``parsed`` is at or below the boundary when it is at or below v
    cmpkey-wise, or when it is in v's local family.
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

    ``parsed`` is at or below the boundary when it is at or below v
    cmpkey-wise, or when it is in v's post family.
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
        # In v's post family: same dev as v (V itself + V+local), or any
        # post-release of V.
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
        # ``-inf`` has no inclusive/exclusive distinction; normalize so the
        # two spellings sort and hash the same instead of comparing equal in
        # one method and unequal in another.
        self.inclusive = False if version is None else inclusive
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
        # See :class:`LowerBound` for the normalization rationale.
        self.inclusive = False if version is None else inclusive
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
FULL_RANGE: tuple[Interval, ...] = ((NEG_INF, POS_INF),)


def _after_locals_successor(version: Version) -> Version:
    """Smallest real version strictly above ``AFTER_LOCALS(version)``.

    When V has a dev segment, the next real version is V with ``dev+1``;
    any post or pre-release segments stay put. Otherwise AFTER_LOCALS(V)
    sits just below V.post0, so its successor is V.post0.dev0
    (V.post(N+1).dev0 when V is itself a post-release).
    """
    if version.dev is not None:
        return version.__replace__(dev=version.dev + 1, local=None)
    next_post = (version.post + 1) if version.post is not None else 0
    return version.__replace__(post=next_post, dev=0, local=None)


def _nearest_non_prerelease(version: Version) -> Version:
    """Smallest non-pre-release at or above a pre-release version.

    An a/b/rc pre-release sorts below its bare release (1.0a1.post2 < 1.0),
    so the nearest non-pre strips pre/post/dev/local. A dev-only release
    sits just below release[.postN] (1.0.post0.dev0 < 1.0.post0), so it
    keeps post and strips only dev/local.
    """
    if version.pre is not None:
        return version.__replace__(pre=None, post=None, dev=None, local=None)
    return version.__replace__(dev=None, local=None)


def _lowest_release_at_or_above(
    value: Version | BoundaryVersion | None,
) -> Version:
    """Lower bound on the smallest non-pre-release at or above value.

    Exact for every case the prerelease-only check needs, except an
    AFTER_POSTS(final) boundary, where it deliberately undershoots (see
    below). A ``None`` value means an unbounded (-inf) lower, whose
    nearest non-pre-release at or above is ``0`` (the smallest final).
    """
    if value is None:
        return Version("0")

    if isinstance(value, BoundaryVersion):
        inner_version = value.version

        if inner_version.is_prerelease:
            return _nearest_non_prerelease(inner_version)

        # AFTER_LOCALS(1.0) -> 1.0.post0; AFTER_LOCALS(1.0.post0) -> 1.0.post1.
        # This ignores value.kind: for an AFTER_POSTS(final) boundary it
        # undershoots (e.g. AFTER_POSTS(1.0) -> 1.0.post0), which is fine.
        # An AFTER_POSTS lower bound always has a longer release above it
        # (e.g. 1.0.0...1), so the caller must treat it as not
        # prerelease-only; overshooting here would wrongly mark satisfiable
        # ranges like >1.0,<1.0.1 as prerelease-only.
        next_post = (inner_version.post + 1) if inner_version.post is not None else 0
        return inner_version.__replace__(post=next_post, local=None)

    if not value.is_prerelease:
        return value

    return _nearest_non_prerelease(value)


def ranges_are_prerelease_only(ranges: Sequence[Interval]) -> bool:
    """``True`` when every range in ranges contains only pre-releases.

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


def range_is_empty(lower: LowerBound, upper: UpperBound) -> bool:
    """True when the range ``(lower, upper)`` contains no versions."""
    # An exclusive upper bound at or below the global minimum admits
    # nothing: no version is below 0.dev0. Inclusive ``<=0.dev0`` is the
    # singleton {0.dev0} (non-empty), so require an exclusive bound. A
    # BoundaryVersion upper sorts above _MIN_VERSION, never at or below it.
    upper_version = upper.version
    if (
        upper_version is not None
        and not upper.inclusive
        and not isinstance(upper_version, BoundaryVersion)
        and upper_version <= _MIN_VERSION
    ):
        return True

    lower_version = lower.version
    if lower_version is None or upper_version is None:
        return False

    # An AFTER_LOCALS(V) lower bound has a bounded successor: the smallest
    # real version above it is V.post0.dev0. The interval holds nothing when
    # the upper bound sits below that successor. AFTER_POSTS needs no such
    # check: release tuples extend without limit, so it has no bounded
    # successor and its ordering against a real upper is already exact.
    if (
        isinstance(lower_version, BoundaryVersion)
        and lower_version.kind == BoundaryKind.AFTER_LOCALS
        and not isinstance(upper_version, BoundaryVersion)
    ):
        successor = _after_locals_successor(lower_version.version)
        if upper_version == successor:
            return not upper.inclusive
        return upper_version < successor

    if lower_version == upper_version:
        return not (lower.inclusive and upper.inclusive)
    return lower_version > upper_version


def canonical_lower(lower: LowerBound) -> LowerBound:
    """Collapse a bottom-anchored inclusive lower bound to ``-inf``.

    An inclusive lower at the global minimum (0.dev0) admits everything,
    same as no lower bound, so it canonicalizes to ``NEG_INF``. Keeping
    both forms apart breaks complement-of-complement identity.
    """
    version = lower.version
    if (
        version is not None
        and not isinstance(version, BoundaryVersion)
        and lower.inclusive
        and version <= _MIN_VERSION
    ):
        return NEG_INF
    return lower


def resolve_prereleases(
    configured: bool | None,
    autodetected: bool | None,
) -> bool | None:
    """Resolve a specifier's default pre-release policy.

    The constructor ``configured`` value wins; otherwise an autodetected
    ``True`` propagates, while an autodetected ``False`` / ``None`` falls back
    to the PEP 440 default (``None``). Used to tag a
    :class:`~packaging.ranges.VersionRange` so it filters like its specifier.
    """
    if configured is not None:
        return configured
    if autodetected:
        return True
    return None


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
    """Filter iterable against precomputed version ranges.

    With ``prereleases=None``, the PEP 440 default applies: pre-releases
    are excluded unless no final matches, in which case buffered
    pre-releases come out at the end.
    """
    # PEP 440 default: yield finals immediately and buffer pre-releases
    # until at least one final has been emitted.
    if prereleases is None:
        nonfinal_buffer: list[Any] = []
        found_final = False

        # Hot path: a single range comes straight out of one Specifier
        # or a SpecifierSet that folds to one contiguous range.
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

        # Multi-range path: try each range, yield on the first hit.
        predicates = tuple((lower.above, upper.below) for lower, upper in ranges)
        for item in iterable:
            parsed = coerce_version(item if key is None else key(item))
            if parsed is None:
                continue
            for above, below in predicates:
                if above is not None and not above(parsed):
                    break
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

    # Hot path: single range, explicit prerelease policy.
    if len(ranges) == 1:
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

    # Multi-range path, explicit prerelease policy.
    predicates = tuple((lower.above, upper.below) for lower, upper in ranges)
    for item in iterable:
        parsed = coerce_version(item if key is None else key(item))
        if parsed is None:
            continue
        if exclude_prereleases and parsed.is_prerelease:
            continue
        for above, below in predicates:
            if above is not None and not above(parsed):
                break
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


def _wildcard_ranges(op: str, base: Version) -> tuple[Interval, ...]:
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


def _standard_ranges(
    operator: str,
    version: Version,
    has_local: bool,
) -> tuple[Interval, ...]:
    """Ranges for the standard PEP 440 operators (no wildcard, no ===).

    has_local indicates whether the spec string included a ``+local``
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
        if version.post is not None or version.dev is not None:
            # V already carries post or dev, so PEP 440's exclusive
            # comparison only excludes V's local family; the lower bound
            # is V[AFTER_LOCALS]. Same shape as ``~(<=V)`` so the two
            # round-trip to the same range.
            return (
                (
                    LowerBound(
                        BoundaryVersion(version, BoundaryKind.AFTER_LOCALS),
                        inclusive=False,
                    ),
                    POS_INF,
                ),
            )
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
    # Build AFTER_LOCALS only when needed: with has_local the bound is V
    # itself, and AFTER_LOCALS forbids a local-bearing inner version.
    upper: Version | BoundaryVersion = (
        version if has_local else BoundaryVersion(version, BoundaryKind.AFTER_LOCALS)
    )

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


def bounds_for_spec(
    operator: str,
    version_str: str,
    parsed: Version | None = None,
) -> tuple[Interval, ...]:
    """Canonical bound intervals for one ``(operator, version_string)``.

    Folds wildcard / standard dispatch with the post-canonicalization that
    intersection and complement paths apply, so a single specifier yields the
    same bounds the algebra would. Not for ``===``; that operator carries a
    literal string match handled at the :class:`VersionRange` layer.

    parsed is the already-parsed version_str (or its base for wildcards),
    used to skip a redundant re-parse when the caller already has it cached.
    """
    if version_str.endswith(".*"):
        base = parsed if parsed is not None else coerce_version(version_str[:-2])
        assert base is not None  # the specifier regex guarantees a valid base
        ranges = _wildcard_ranges(operator, base)
    else:
        version = parsed if parsed is not None else coerce_version(version_str)
        assert version is not None  # the specifier regex guarantees a valid version
        ranges = _standard_ranges(operator, version, has_local="+" in version_str)

    # Fast path: skip the canonicalize-and-prune walk for the common
    # case where every interval is already canonical (no inclusive lower
    # collapsible to ``-inf``, no exclusive upper at or below the global
    # minimum that would empty the interval). One bound check per
    # interval beats the generic ``canonical_lower`` + ``range_is_empty``
    # function-call pair on every cold ``_to_ranges`` build.
    for lower, upper in ranges:
        lv = lower.version
        if (
            lv is not None
            and lower.inclusive
            and not isinstance(lv, BoundaryVersion)
            and lv <= _MIN_VERSION
        ):
            break
        uv = upper.version
        if (
            uv is not None
            and not upper.inclusive
            and not isinstance(uv, BoundaryVersion)
            and uv <= _MIN_VERSION
        ):
            break
    else:
        return ranges

    result: list[Interval] = []
    for lower, upper in ranges:
        canonical = canonical_lower(lower)
        if not range_is_empty(canonical, upper):
            result.append((canonical, upper))
    return tuple(result)


def intersect_specifier_bounds(
    per_specifier_bounds: Iterable[tuple[Interval, ...]],
) -> tuple[Interval, ...]:
    """Intersect per-specifier bounds into a single canonical tuple.

    Universe-blind: callers pass the already-resolved per-spec bounds and
    handle admit literals themselves. Short-circuits once an intermediate
    intersection goes empty, since no further fold can revive it.
    """
    result: Sequence[Interval] | None = None
    for sub in per_specifier_bounds:
        if result is None:
            result = sub
        elif not result:
            break
        else:
            result = intersect_ranges(result, sub)
    if result is None:  # pragma: no cover - callers guard non-empty input
        raise RuntimeError("intersection over an empty specifier iterable")
    return tuple(result)
