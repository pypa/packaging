# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.
"""Public :class:`VersionRange` API.

A set-algebra view of the versions accepted by a
:class:`~packaging.specifiers.SpecifierSet`. Ranges support intersection,
union, complement, and difference; membership and filtering match the
originating specifier set.

.. testsetup::

    from packaging.ranges import VersionRange
    from packaging.specifiers import SpecifierSet
    from packaging.version import Version
"""

from __future__ import annotations

import enum
import typing
from typing import (
    TYPE_CHECKING,
    Any,
    TypeVar,
    Union,
)

from ._ranges import (
    FULL_RANGE,
    MIN_VERSION,
    NEG_INF,
    POS_INF,
    BoundaryKind,
    BoundaryVersion,
    LowerBound,
    UpperBound,
    coerce_version,
    filter_by_ranges,
    intersect_ranges,
    least_version_above,
    matches_bounds_only,
    range_is_empty,
    ranges_are_prerelease_only,
)
from .version import Version

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator, Sequence

    from ._ranges import Interval
    from .specifiers import SpecifierSet


__all__ = ["VersionRange"]

T = TypeVar("T")
UnparsedVersion = Union[Version, str]
UnparsedVersionVar = TypeVar("UnparsedVersionVar", bound=UnparsedVersion)


class _SetOp(enum.Enum):
    """The binary set operation ``_combine_literals`` resolves over ``===`` literals."""

    INTERSECTION = enum.auto()
    UNION = enum.auto()
    DIFFERENCE = enum.auto()


def __dir__() -> list[str]:
    return __all__


# Range algebra: intersection and the empty-interval test live in the engine
# (``intersect_ranges`` / ``range_is_empty``); union and complement are only
# needed here, so they live in this module.


def _union_ranges(
    left: Sequence[Interval],
    right: Sequence[Interval],
) -> list[Interval]:
    """Union two sorted, non-overlapping interval lists.

    A linear merge over the two pre-sorted inputs followed by a single
    coalescing pass: adjacent or overlapping intervals collapse so the result
    is itself sorted and non-overlapping.
    """
    if not left:
        return list(right)
    if not right:
        return list(left)

    merged_input: list[Interval] = []
    left_index = right_index = 0
    while left_index < len(left) and right_index < len(right):
        if left[left_index][0] <= right[right_index][0]:
            merged_input.append(left[left_index])
            left_index += 1
        else:
            merged_input.append(right[right_index])
            right_index += 1
    merged_input.extend(left[left_index:])
    merged_input.extend(right[right_index:])

    merged: list[Interval] = [merged_input[0]]
    for lower, upper in merged_input[1:]:
        prev_lower, prev_upper = merged[-1]

        if (
            prev_upper.version is None
            or lower.version is None
            or prev_upper.version > lower.version
        ):
            overlaps = True
        elif prev_upper.version == lower.version:
            overlaps = prev_upper.inclusive or lower.inclusive
        else:
            # An ordering gap may still hold no version when the two bounds
            # straddle a synthetic boundary; merge across an empty gap to
            # stay canonical.
            gap_lower = LowerBound(prev_upper.version, not prev_upper.inclusive)
            gap_upper = UpperBound(lower.version, not lower.inclusive)
            overlaps = range_is_empty(gap_lower, gap_upper)

        if overlaps:
            merged[-1] = (prev_lower, max(prev_upper, upper))
        else:
            merged.append((lower, upper))

    return merged


def _complement_ranges(ranges: Sequence[Interval]) -> list[Interval]:
    """Complement a sorted, non-overlapping interval list.

    Yields the gaps between intervals plus a leading gap before the first and
    a trailing gap after the last. Bound inclusivity flips so that
    complement-of-complement round-trips back to the input.
    """
    if not ranges:
        return list(FULL_RANGE)

    result: list[Interval] = []
    prev_upper: UpperBound | None = None

    for lower, upper in ranges:
        if prev_upper is None:
            # Leading gap below the first interval. Every range reaching here is
            # floor-canonical: ``_canonical_floor`` has already folded an
            # inclusive lower at or below ``0.dev0`` into ``-inf``. So a finite
            # first lower always leaves a non-empty gap down to ``-inf``, while a
            # ``-inf`` lower leaves no leading gap at all.
            if lower.version is not None:
                gap_upper = UpperBound(lower.version, not lower.inclusive)
                result.append((NEG_INF, gap_upper))
        else:
            gap_lower = LowerBound(prev_upper.version, not prev_upper.inclusive)
            gap_upper = UpperBound(lower.version, not lower.inclusive)
            # Input intervals are canonical (sorted, disjoint, non-touching),
            # so the gap between two of them always holds at least one version.
            result.append((gap_lower, gap_upper))
        prev_upper = upper

    # The empty-input early return guarantees the loop ran.
    assert prev_upper is not None
    if prev_upper.version is not None:
        gap_lower = LowerBound(prev_upper.version, not prev_upper.inclusive)
        result.append((gap_lower, POS_INF))

    return result


def _canonical_floor(bounds: tuple[Interval, ...]) -> tuple[Interval, ...]:
    """Collapse the PEP 440 floor in a sorted interval list.

    Only the first interval can touch ``0.dev0`` (the minimum version). An
    inclusive lower at or below it admits everything below, the same as
    ``-inf``, so ``>=0.dev0`` becomes the one canonical full range. An
    exclusive upper at or below it leaves the interval empty, so it is dropped.
    """
    if not bounds:
        return bounds

    lower, upper = bounds[0]
    if range_is_empty(NEG_INF, upper):
        return bounds[1:]

    if (
        lower.inclusive
        and isinstance(lower.version, Version)
        and lower.version <= MIN_VERSION
    ):
        return ((NEG_INF, upper), *bounds[1:])

    return bounds


def _predecessor_boundary(version: Version) -> BoundaryVersion | None:
    """The boundary whose least successor is *version*, or ``None``.

    Inverse of :func:`~packaging._ranges.least_version_above`. A plain version
    that is exactly such a successor (``1.0a2.dev0`` sits just above
    ``AFTER_POSTS(1.0a1)``) folds back to that boundary, so ``>=1.0a2.dev0`` and
    ``>1.0a1`` share one form. The proposed boundary is confirmed by
    round-tripping through ``least_version_above``.
    """
    # Only a least successor carries a dev segment, so nothing else can fold.
    if version.dev is None:
        return None

    candidate: BoundaryVersion | None = None
    if version.pre is not None and version.dev == 0 and version.post is None:
        # 1.0a2.dev0 -> AFTER_POSTS(1.0a1)
        kind, number = version.pre
        if number >= 1:
            candidate = BoundaryVersion(
                version.__replace__(pre=(kind, number - 1), dev=None),
                BoundaryKind.AFTER_POSTS,
            )
    elif version.dev >= 1:
        # 1.0.dev3 -> AFTER_LOCALS(1.0.dev2)
        candidate = BoundaryVersion(
            version.__replace__(dev=version.dev - 1), BoundaryKind.AFTER_LOCALS
        )
    elif version.dev == 0 and version.post is not None:
        # 1.0.post1.dev0 -> AFTER_LOCALS(1.0.post0); 1.0.post0.dev0 -> AFTER_LOCALS(1.0)
        base = (
            version.__replace__(post=None, dev=None)
            if version.post == 0
            else version.__replace__(post=version.post - 1, dev=None)
        )
        candidate = BoundaryVersion(base, BoundaryKind.AFTER_LOCALS)

    if candidate is not None and least_version_above(candidate) == version:
        return candidate
    return None


def _canonicalize(bounds: tuple[Interval, ...]) -> tuple[Interval, ...]:
    """Fold least-successor bounds to their boundary form.

    ``>=1.0a2.dev0`` and ``>1.0a1`` denote the same set, so both must reduce to
    one representation for ``==`` and ``hash`` to agree. An inclusive lower or
    exclusive upper sitting on a boundary's least successor becomes that
    boundary; the engine's emptiness check has already dropped the synthetic
    gaps such intervals would otherwise leave.
    """
    result: list[Interval] = []
    for lower, upper in bounds:
        new_lower, new_upper = lower, upper

        if isinstance(lower.version, Version) and lower.inclusive:
            boundary = _predecessor_boundary(lower.version)
            if boundary is not None:
                new_lower = LowerBound(boundary, inclusive=False)

        if isinstance(upper.version, Version) and not upper.inclusive:
            boundary = _predecessor_boundary(upper.version)
            if boundary is not None:
                new_upper = UpperBound(boundary, inclusive=True)

        result.append((new_lower, new_upper))
    return tuple(result)


def _struct_admits(
    bounds: tuple[Interval, ...], admit_arbitrary: bool, literal: str
) -> bool:
    """True when the bounds (plus arbitrary admission) admit ``literal``.

    Skips the explicit admit/reject sets, which the caller layers on top. A
    non-version string matches via ``admit_arbitrary`` only on full bounds;
    on narrower bounds the flag is metadata only.
    """
    parsed = coerce_version(literal)
    if parsed is None:
        return admit_arbitrary and bounds == FULL_RANGE

    return matches_bounds_only(bounds, parsed)


# Repr helpers:


def _bound_version_str(value: BoundaryVersion | Version) -> str:
    """Printout for a bound's inner value, kind-tagged for boundaries."""
    if isinstance(value, BoundaryVersion):
        return f"{value.version}[{value.kind.name}]"
    return str(value)


def _format_lower(bound: LowerBound) -> str:
    if bound.version is None:
        return "(-inf"
    bracket = "[" if bound.inclusive else "("
    return f"{bracket}{_bound_version_str(bound.version)}"


def _format_upper(bound: UpperBound) -> str:
    if bound.version is None:
        return "+inf)"
    bracket = "]" if bound.inclusive else ")"
    return f"{_bound_version_str(bound.version)}{bracket}"


def _format_intervals(intervals: Sequence[Interval]) -> str:
    """Render a sorted interval list as ``lower, upper | lower, upper``."""
    return " | ".join(
        f"{_format_lower(lower)}, {_format_upper(upper)}" for lower, upper in intervals
    )


class VersionRange:
    """A set of :class:`~packaging.version.Version` values accepted by a
    :class:`~packaging.specifiers.SpecifierSet`.

    Construct via :meth:`~packaging.specifiers.SpecifierSet.to_range`, or with
    the :meth:`full`, :meth:`empty`, and :meth:`singleton` class methods.
    Compose with :meth:`intersection`, :meth:`union`, :meth:`complement`, and
    :meth:`difference` (or the ``&`` / ``|`` / ``~`` / ``-`` operators). Test
    membership with ``in`` or :meth:`contains`, filter an iterable with
    :meth:`filter`.

    The configured pre-release policy of the originating specifier set carries
    onto the range and controls whether pre-releases are admitted under ``in``,
    :meth:`contains`, and :meth:`filter`. With no configured policy,
    :meth:`filter` also admits pre-releases in the autodetected opt-in region
    (the versions a pre-release-naming specifier asked for). Set algebra keeps
    that opt-in scoped to those versions, so unrelated pre-releases are not
    admitted wholesale.

    :meth:`intersection`, :meth:`union`, :meth:`difference`, and the
    :meth:`is_subset` / :meth:`is_superset` / :meth:`is_disjoint` predicates
    require both operands to share the same configured policy.

    >>> r = SpecifierSet(">=1.0,<2.0").to_range()
    >>> "1.5" in r
    True
    >>> "2.0" in r
    False
    >>> SpecifierSet(">=2.0,<1.0").to_range().is_empty
    True

    PEP 440's ``===`` operator matches a candidate string verbatim
    (case-insensitive) rather than a set of versions. Ranges built from
    ``===`` specifiers still support membership and set operations; matching
    follows the literal-equality rule. A ``===`` literal that names a
    pre-release is admitted under the default policy by both :meth:`contains`
    and :meth:`filter`, since it was named outright.

    .. versionadded:: 26.3
    """

    __slots__ = (
        "_admit",
        "_admit_arbitrary",
        "_bounds",
        "_pre_region",
        "_prereleases_configured",
        "_reject",
    )

    #: The disjoint, sorted, non-overlapping interval list.
    _bounds: tuple[Interval, ...]

    #: Whether this range matches non-version strings as well as versions.
    #: True only by construction on ``SpecifierSet("")`` / :meth:`full`. The flag
    #: rides set algebra but is inert except at full bounds (see
    #: :meth:`_arbitrary_active`). An intersection or difference that empties
    #: out the bounds drops it (``full() & ~full()`` is plain empty);
    #: :meth:`complement` and a union of empty-bounds operands keep it, so
    #: ``~~full() == full()`` and ``~full() | ~full() == ~full()``. Part of
    #: equality, since membership reads it.
    _admit_arbitrary: bool

    #: Case-folded strings the range admits in addition to its bounds.
    #: ``===wat`` produces ``_admit = {"wat"}``.
    _admit: frozenset[str]

    #: Case-folded strings the range rejects (overrides ``_admit`` and the
    #: bounds). Populated by :meth:`complement` of an admit-bearing range and by
    #: literal resolution in :meth:`_combine_literals`.
    _reject: frozenset[str]

    #: Sorted, disjoint intervals where pre-releases are force-admitted under
    #: the PEP 440 default policy (a ``None`` ``prereleases`` argument and no
    #: configured override). The opt-in flows only from the pre-release-naming
    #: specifiers that built the range. :meth:`_build` clips the region to the
    #: bounds, so it is always a subset of them: an opt-in that overflowed its
    #: own cap cannot ride a later union into versions no specifier asked for.
    #: :meth:`union` and :meth:`intersection` accumulate the operands' clipped
    #: regions and re-clip to the result bounds; :meth:`difference` keeps only
    #: the minuend's; and :meth:`complement` drops it, since an exclusion grants
    #: no opt-in. Equality keys on the clipped region, so it stays a congruence.
    _pre_region: tuple[Interval, ...]

    #: Raw configured pre-release override of the originating specifier set
    #: (an explicit ``True`` / ``False``, else ``None``). When set, :meth:`_build`
    #: forces ``_pre_region`` empty since the policy governs globally.
    #: :meth:`intersection` and :meth:`union` require it to match on both
    #: operands. Part of equality.
    _prereleases_configured: bool | None

    def __new__(cls, *args: object, **kwargs: object) -> VersionRange:  # noqa: PYI034
        raise TypeError(
            "cannot create 'VersionRange' instances directly; use "
            "SpecifierSet.to_range(), VersionRange.full(), "
            "VersionRange.empty(), or VersionRange.singleton() instead"
        )

    @classmethod
    def _build(
        cls,
        bounds: tuple[Interval, ...],
        admit: frozenset[str] = frozenset(),
        reject: frozenset[str] = frozenset(),
        admit_arbitrary: bool = False,
        *,
        pre_region: tuple[Interval, ...] = (),
        prereleases_configured: bool | None = None,
    ) -> VersionRange:
        """Internal factory; bypasses :meth:`__new__`.

        Canonicalizes the bounds so equal version sets share one representation,
        then drops admit literals the bounds already admit and reject literals
        the bounds do not match anyway. Reject wins over admit on overlap. The
        pre-release policy is set here and never reassigned afterwards;
        ``pre_region`` is canonicalized like the bounds and clipped to them,
        or dropped when a configured policy makes it inert.
        """
        bounds = _canonicalize(bounds)

        if admit and reject:
            admit = admit - reject
        if admit:
            admit = frozenset(
                literal
                for literal in admit
                if not _struct_admits(bounds, admit_arbitrary, literal)
            )
        if reject:
            reject = frozenset(
                literal
                for literal in reject
                if _struct_admits(bounds, admit_arbitrary, literal)
            )

        instance = object.__new__(cls)
        instance._bounds = bounds
        instance._admit = admit
        instance._reject = reject
        instance._admit_arbitrary = admit_arbitrary
        instance._prereleases_configured = prereleases_configured

        # A configured policy makes the region inert, so drop it. Otherwise fold
        # least-successor bounds (_from_specifier_set passes the region unfolded),
        # so ``>1.0a1`` and ``>=1.0a2.dev0`` carry the same region, then clip it
        # to the bounds so the opt-in never reaches past the range's own versions.
        if prereleases_configured is not None or not pre_region:
            instance._pre_region = ()
        else:
            instance._pre_region = tuple(
                intersect_ranges(_canonicalize(pre_region), bounds)
            )

        return instance

    def _has_literals(self) -> bool:
        return bool(self._admit) or bool(self._reject)

    def _arbitrary_active(self) -> bool:
        """True when ``_admit_arbitrary`` actually admits non-version strings.

        The flag rides through set algebra but only fires admission on full
        bounds; on narrower bounds it is metadata awaiting a later widening.
        """
        return self._admit_arbitrary and self._bounds == FULL_RANGE

    def _is_plain(self) -> bool:
        """True when membership is decided by ``_bounds`` alone, enabling the
        bounds-only fast paths in :meth:`is_subset` and :meth:`is_disjoint`.
        """
        return (
            not self._has_literals()
            and not self._admit_arbitrary
            and self._prereleases_configured is not False
        )

    def _check_policy_compat(self, other: VersionRange) -> None:
        """Refuse combining ranges with different pre-release policies."""
        if not isinstance(other, VersionRange):
            raise TypeError(f"expected VersionRange, got {type(other).__name__}")
        if self._prereleases_configured != other._prereleases_configured:
            raise ValueError(
                "Cannot combine VersionRange operands with different "
                f"pre-release policies: {self._prereleases_configured!r} "
                f"and {other._prereleases_configured!r}"
            )

    def _merged_region(self, other: VersionRange) -> tuple[Interval, ...]:
        """Union of ``self`` and ``other``'s opt-in regions.

        Used by :meth:`union` and :meth:`intersection`; :meth:`_build` clips the
        merge to the result bounds. A configured operand carries an empty region,
        so it contributes nothing to the merge.
        """
        # Reuse an operand's canonical tuple when only one side has a region;
        # an empty side contributes nothing to the union.
        if not other._pre_region:
            return self._pre_region
        if not self._pre_region:
            return other._pre_region

        # Both sides carry a region; merge them. _build re-canonicalizes and
        # clips, so the plain union is fine here.
        return tuple(_union_ranges(self._pre_region, other._pre_region))

    def _with_policy(
        self, *, pre_region: tuple[Interval, ...], configured: bool | None
    ) -> VersionRange:
        """A structural copy of this range carrying the given pre-release policy."""
        return self._build(
            self._bounds,
            admit=self._admit,
            reject=self._reject,
            admit_arbitrary=self._admit_arbitrary,
            pre_region=pre_region,
            prereleases_configured=configured,
        )

    @classmethod
    def empty(cls, *, prereleases: bool | None = None) -> VersionRange:
        """Return the empty range. No version satisfies it.

        >>> VersionRange.empty().is_empty
        True
        >>> "1.0" in VersionRange.empty()
        False
        """
        return cls._build((), prereleases_configured=prereleases)

    @classmethod
    def full(
        cls, *, admit_arbitrary: bool = True, prereleases: bool | None = None
    ) -> VersionRange:
        """Return the full range. Every PEP 440 version satisfies it.

        ``admit_arbitrary=False`` restricts the range to PEP 440 versions only
        (matching the same versions as ``SpecifierSet(">=0.dev0").to_range()``);
        its complement is :meth:`empty`. The flag propagates through set algebra
        and is part of equality. Default ``True`` so that ``r & full()``
        preserves ``r``'s own flag structurally.

        >>> "1.0" in VersionRange.full()
        True
        >>> "wat" in VersionRange.full()
        True
        >>> "wat" in VersionRange.full(admit_arbitrary=False)
        False
        """
        return cls._build(
            FULL_RANGE,
            admit_arbitrary=admit_arbitrary,
            prereleases_configured=prereleases,
        )

    @classmethod
    def singleton(
        cls, version: Version | str, *, prereleases: bool | None = None
    ) -> VersionRange:
        """Return the strict singleton range ``{version}``.

        Built as the closed interval ``[version, version]`` with strict
        equality. ``Specifier("==V")`` matches ``V+local`` too, so the strict
        singleton is narrower:

        >>> "1.0+local" in VersionRange.singleton("1.0")
        False
        >>> "1.0+local" in SpecifierSet("==1.0").to_range()
        True

        :raises packaging.version.InvalidVersion: if version is a string that
            does not parse as a PEP 440 version.
        """
        if not isinstance(version, Version):
            version = Version(version)

        lower = LowerBound(version, True)
        upper = UpperBound(version, True)

        # Collapse the floor: nothing sorts below ``MIN_VERSION``, so the
        # ``0.dev0`` singleton is ``(-inf, 0.dev0]`` in canonical form.
        return cls._build(
            _canonical_floor(((lower, upper),)),
            prereleases_configured=prereleases,
        )

    def intersection(self, other: VersionRange) -> VersionRange:
        """Range containing exactly the versions in both self and other.

        Both operands must share the same configured pre-release policy;
        otherwise :exc:`ValueError` is raised.

        >>> a = SpecifierSet(">=1.0").to_range()
        >>> b = SpecifierSet("<2.0").to_range()
        >>> a.intersection(b) == SpecifierSet(">=1.0,<2.0").to_range()
        True
        """
        self._check_policy_compat(other)

        configured = self._prereleases_configured
        new_bounds = tuple(intersect_ranges(self._bounds, other._bounds))
        new_region = self._merged_region(other)

        # An empty intersection (e.g. ``full() & ~full()``) is the empty range,
        # so it drops the arbitrary flag, agreeing with difference when the
        # subtrahend consumes the bounds.
        combined_arb = (
            self._admit_arbitrary and other._admit_arbitrary and bool(new_bounds)
        )

        if not self._has_literals() and not other._has_literals():
            return self._build(
                new_bounds,
                admit_arbitrary=combined_arb,
                pre_region=new_region,
                prereleases_configured=configured,
            )

        return self._combine_literals(
            other,
            new_bounds,
            op=_SetOp.INTERSECTION,
            admit_arbitrary=combined_arb,
            pre_region=new_region,
            prereleases_configured=configured,
        )

    def union(self, other: VersionRange) -> VersionRange:
        """Range containing every version in self or other.

        Both operands must share the same configured pre-release policy;
        otherwise :exc:`ValueError` is raised.

        >>> a = VersionRange.singleton("1.0")
        >>> b = VersionRange.singleton("2.0")
        >>> "1.0" in a.union(b) and "2.0" in a.union(b)
        True
        >>> "1.5" in a.union(b)
        False
        """
        self._check_policy_compat(other)

        configured = self._prereleases_configured
        new_bounds = tuple(_union_ranges(self._bounds, other._bounds))
        new_region = self._merged_region(other)

        # An empty-bounds operand (e.g. ``~full()``) carries an inert arbitrary
        # flag only to keep complement an involution; it admits nothing, so it
        # must not revive arbitrary admission as the union re-widens the bounds.
        if new_bounds:
            combined_arb = (self._admit_arbitrary and bool(self._bounds)) or (
                other._admit_arbitrary and bool(other._bounds)
            )
        else:
            # Nothing widened, so keeping the flags keeps ``r | r == r``.
            combined_arb = self._admit_arbitrary or other._admit_arbitrary

        if not self._has_literals() and not other._has_literals():
            return self._build(
                new_bounds,
                admit_arbitrary=combined_arb,
                pre_region=new_region,
                prereleases_configured=configured,
            )

        return self._combine_literals(
            other,
            new_bounds,
            op=_SetOp.UNION,
            admit_arbitrary=combined_arb,
            pre_region=new_region,
            prereleases_configured=configured,
        )

    def complement(self) -> VersionRange:
        """Range containing every version not in self.

        Preserves the configured pre-release policy. On the version set, double
        negation holds for a range with no ``===`` literals (the arbitrary-string
        flag round-trips, so ``~~full() == full()``); for ``===`` ranges
        complement is one-way. The opt-in region is not restored (see below).

        The opt-in region is dropped: a complement is an exclusion, and an
        exclusion expresses no pre-release preference. This is what lets
        ``a & ~b`` shed ``b``'s opt-in, so an excluded ``b`` never force-admits a
        pre-release into the result. Complement stays involutive on the version
        set, but not on the opt-in region: ``~~r`` covers the same versions as
        ``r`` yet force-admits none of its pre-releases.

        >>> r = SpecifierSet(">=1.0").to_range()
        >>> "0.5" in r.complement()
        True
        >>> "1.5" in r.complement()
        False
        >>> r.complement().complement() == r
        True
        """
        # Complement swaps literal admission: what the range rejects, its
        # complement admits.
        return self._build(
            tuple(_complement_ranges(self._bounds)),
            admit=self._reject,
            reject=self._admit,
            admit_arbitrary=self._admit_arbitrary,
            pre_region=(),
            prereleases_configured=self._prereleases_configured,
        )

    def difference(self, other: VersionRange) -> VersionRange:
        """Range containing the versions in self but not in other.

        Matches ``self & ~other`` on both the version set and the opt-in region;
        ``other`` acts as a bounds-only exclusion that grants no opt-in. They
        part only on non-version-string admission, whose complement is one-way:
        a ``===`` literal stays when ``self`` admits it and ``other`` does not,
        and the arbitrary-string flag is kept from ``self``. Both operands must
        share the same configured pre-release policy (as :meth:`intersection`
        and :meth:`union` require); otherwise :exc:`ValueError` is raised.
        ``a - empty()`` returns a range equal to ``a``.

        >>> a = SpecifierSet(">=1.0").to_range()
        >>> b = SpecifierSet(">=2.0").to_range()
        >>> "1.5" in a.difference(b)
        True
        >>> "2.0" in a.difference(b)
        False
        >>> a.difference(VersionRange.empty()) == a
        True
        """
        self._check_policy_compat(other)

        # Subtracting a nothing-admitting set is a no-op. Short-circuit so an
        # empty-bounds self (e.g. ``~full()``) keeps its arbitrary-string flag,
        # which the general path would drop.
        if not other._bounds and not other._admit:
            return self

        # Bound complement is two-way, so subtracting other's versions is an
        # intersection with its gaps.
        new_bounds = tuple(
            intersect_ranges(self._bounds, _complement_ranges(other._bounds))
        )

        # Match ``self & ~other`` on the opt-in region: a complement carries no
        # opt-in, so only ``self``'s region survives. ``other`` acts as a
        # bounds-only exclusion. A configured ``self`` keeps no region.
        new_region: tuple[Interval, ...] = ()
        if self._prereleases_configured is None:
            new_region = self._pre_region

        # Keep self's arbitrary admission. Other only removes it at full bounds,
        # where nothing survives, so the empty result drops it (as in
        # :meth:`intersection`) with no separate other-side test.
        combined_arb = self._admit_arbitrary and bool(new_bounds)

        if not self._has_literals() and not other._has_literals():
            return self._build(
                new_bounds,
                admit_arbitrary=combined_arb,
                pre_region=new_region,
                prereleases_configured=self._prereleases_configured,
            )

        return self._combine_literals(
            other,
            new_bounds,
            op=_SetOp.DIFFERENCE,
            admit_arbitrary=combined_arb,
            pre_region=new_region,
            prereleases_configured=self._prereleases_configured,
        )

    def _combine_literals(
        self,
        other: VersionRange,
        new_bounds: tuple[Interval, ...],
        *,
        op: _SetOp,
        admit_arbitrary: bool,
        pre_region: tuple[Interval, ...],
        prereleases_configured: bool | None,
    ) -> VersionRange:
        """Resolve admit/reject for ``self`` ``op`` ``other`` over their literals."""
        admits: set[str] = set()
        rejects: set[str] = set()

        # Each literal is decided independently of the others.
        for literal in self._admit | self._reject | other._admit | other._reject:
            self_in = self._matches_literal(literal)
            other_in = other._matches_literal(literal)

            if op is _SetOp.INTERSECTION:
                want = self_in and other_in
            elif op is _SetOp.UNION:
                want = self_in or other_in
            else:
                want = self_in and not other_in

            if want:
                admits.add(literal)
            else:
                rejects.add(literal)

        return self._build(
            new_bounds,
            admit=frozenset(admits),
            reject=frozenset(rejects),
            admit_arbitrary=admit_arbitrary,
            pre_region=pre_region,
            prereleases_configured=prereleases_configured,
        )

    def _matches_literal(self, literal: str) -> bool:
        """Whether literal (case-folded) matches this range's predicate."""
        if literal in self._reject:
            return False
        if literal in self._admit:
            return True

        parsed = coerce_version(literal)
        if parsed is None:
            return self._arbitrary_active()
        return matches_bounds_only(self._bounds, parsed)

    def __and__(self, other: object) -> VersionRange:
        """Operator alias for :meth:`intersection`."""
        if not isinstance(other, VersionRange):
            return NotImplemented
        return self.intersection(other)

    def __or__(self, other: object) -> VersionRange:
        """Operator alias for :meth:`union`."""
        if not isinstance(other, VersionRange):
            return NotImplemented
        return self.union(other)

    def __invert__(self) -> VersionRange:
        """Operator alias for :meth:`complement`."""
        return self.complement()

    def __sub__(self, other: object) -> VersionRange:
        """Operator alias for :meth:`difference`."""
        if not isinstance(other, VersionRange):
            return NotImplemented
        return self.difference(other)

    def is_subset(self, other: VersionRange) -> bool:
        """Return whether every member of self is also a member of other.

        On versions and ``===`` literals this is
        ``self.difference(other).is_empty``: subtracting other leaves nothing
        behind. A live arbitrary admission (the flag at full bounds) is only a
        subset of another live one.

        Both operands must share the same configured pre-release policy;
        otherwise :exc:`ValueError` is raised.

        >>> inner = SpecifierSet(">=1.5,<1.8").to_range()
        >>> outer = SpecifierSet(">=1.0,<2.0").to_range()
        >>> inner.is_subset(outer)
        True
        >>> outer.is_subset(inner)
        False
        >>> VersionRange.empty().is_subset(outer)
        True
        """
        self._check_policy_compat(other)

        # A live arbitrary admission has non-version strings as members, which
        # no bounds cover; only another live admission contains them.
        if self._arbitrary_active() and not other._arbitrary_active():
            return False

        # Plain ranges: subset reduces to bounds containment, no algebra needed.
        if self._is_plain() and other._is_plain():
            return not intersect_ranges(self._bounds, _complement_ranges(other._bounds))

        # difference (unlike intersection with the one-way complement) resolves
        # ``===`` literals against both operands, so it stays correct for them.
        return self.difference(other).is_empty

    def is_superset(self, other: VersionRange) -> bool:
        """Return whether every member of other is also a member of self.

        The mirror of :meth:`is_subset`: ``a.is_superset(b)`` is
        ``b.is_subset(a)``.

        Both operands must share the same configured pre-release policy;
        otherwise :exc:`ValueError` is raised.

        >>> outer = SpecifierSet(">=1.0,<2.0").to_range()
        >>> outer.is_superset(SpecifierSet(">=1.5,<1.8").to_range())
        True
        """
        # Type-guards a non-VersionRange other before delegating to is_subset.
        self._check_policy_compat(other)
        return other.is_subset(self)

    def is_disjoint(self, other: VersionRange) -> bool:
        """Return whether self and other share no member.

        Equivalent to ``(self & other).is_empty``.

        Both operands must share the same configured pre-release policy;
        otherwise :exc:`ValueError` is raised.

        >>> a = SpecifierSet(">=1.0,<2.0").to_range()
        >>> a.is_disjoint(SpecifierSet(">=2.0,<3.0").to_range())
        True
        >>> a.is_disjoint(SpecifierSet(">=1.5,<2.5").to_range())
        False
        """
        self._check_policy_compat(other)

        # Plain ranges: disjointness is an empty bounds intersection.
        if self._is_plain() and other._is_plain():
            return not intersect_ranges(self._bounds, other._bounds)
        return self.intersection(other).is_empty

    @typing.overload
    def filter(
        self,
        iterable: Iterable[UnparsedVersionVar],
        prereleases: bool | None = None,
        key: None = ...,
    ) -> Iterator[UnparsedVersionVar]: ...

    @typing.overload
    def filter(
        self,
        iterable: Iterable[T],
        prereleases: bool | None = None,
        key: Callable[[T], UnparsedVersion] = ...,
    ) -> Iterator[T]: ...

    def filter(
        self,
        iterable: Iterable[Any],
        prereleases: bool | None = None,
        key: Callable[[Any], Version | str] | None = None,
    ) -> Iterator[Any]:
        """Yield items from iterable whose version falls inside the range.

        With prereleases ``None`` the PEP 440 default applies: pre-releases are
        buffered and only emitted if no final release in iterable is in range,
        except that a pre-release inside the autodetected opt-in region, or named
        outright by a ``===`` literal, is force-admitted in place (as
        ``prereleases=True`` would yield it). A flushed buffer comes after
        every in-place yield, so the output is not version-sorted.

        The signature mirrors
        :meth:`~packaging.specifiers.SpecifierSet.filter`.

        >>> r = SpecifierSet(">=1.0,<2.0").to_range()
        >>> list(r.filter(["0.9", "1.5", "2.0"]))
        ['1.5']
        """
        region: tuple[Interval, ...] = ()
        if prereleases is None:
            # The region applies only under the autodetect default; a configured
            # policy governs instead (and then ``_pre_region`` is already empty).
            prereleases = self._prereleases_configured
            region = self._pre_region

        arbitrary_active = self._arbitrary_active()
        if not self._admit and not self._reject and not arbitrary_active:
            # A region spanning the whole bounds force-admits every in-bounds
            # pre-release, i.e. ``prereleases=True``; take the cheaper no-buffer
            # path. (Confined to this branch: the admission path orders arbitrary
            # strings differently under True than under the region.)
            if region and region == self._bounds:
                return filter_by_ranges(self._bounds, iterable, key, True)
            return filter_by_ranges(self._bounds, iterable, key, prereleases, region)
        return self._filter_with_admission(
            iterable, key, prereleases, arbitrary_active, region
        )

    def _filter_with_admission(
        self,
        iterable: Iterable[Any],
        key: Callable[[Any], Version | str] | None,
        prereleases: bool | None,
        arbitrary_active: bool,
        region: tuple[Interval, ...],
    ) -> Iterator[Any]:
        """Filter for ranges with admit/reject literals or live arbitrary
        admission (including the universal ``SpecifierSet("")`` range)."""
        admit_set = self._admit
        reject_set = self._reject

        def admit(item: Any) -> tuple[bool, Version | None, bool]:  # noqa: ANN401
            raw: Version | str = item if key is None else key(item)
            raw_lower = str(raw).lower()

            if reject_set and raw_lower in reject_set:
                return False, None, False
            if admit_set and raw_lower in admit_set:
                # An explicit ``===`` literal names this version outright.
                return True, coerce_version(raw), True

            parsed = coerce_version(raw)
            if parsed is None:
                return arbitrary_active, None, False
            if not matches_bounds_only(self._bounds, parsed):
                return False, None, False
            return True, parsed, False

        if prereleases is True:
            for item in iterable:
                ok, _, _ = admit(item)
                if ok:
                    yield item
            return

        if prereleases is False:
            for item in iterable:
                ok, parsed, _ = admit(item)
                if not ok:
                    continue
                if parsed is not None and parsed.is_prerelease:
                    continue
                yield item
            return

        # PEP 440 default: emit finals eagerly and buffer the other pre-releases,
        # releasing the buffer only if no final ever matches.
        all_nonfinal: list[Any] = []
        arbitrary_strings: list[Any] = []
        found_final = False

        for item in iterable:
            ok, parsed, by_literal = admit(item)
            if not ok:
                continue

            if parsed is None:
                if found_final:
                    yield item
                else:
                    arbitrary_strings.append(item)
                    all_nonfinal.append(item)
                continue

            if not parsed.is_prerelease:
                if not found_final:
                    yield from arbitrary_strings
                    arbitrary_strings.clear()
                    found_final = True
                yield item
                continue

            # A pre-release is force-admitted when it is named outright by a
            # ``===`` literal or falls in the opt-in region, as ``prereleases=True``
            # would yield it; otherwise the PEP 440 default buffers it.
            if by_literal or (region and matches_bounds_only(region, parsed)):
                yield item
                continue

            if not found_final:
                all_nonfinal.append(item)

        if not found_final:
            yield from all_nonfinal

    @classmethod
    def _from_specifier_set(cls, specifier_set: SpecifierSet) -> VersionRange:
        """Build the range accepted by ``specifier_set``.

        Friend constructor for :meth:`~packaging.specifiers.SpecifierSet.to_range`.
        The intersection of every specifier in the set: an empty set yields the
        full range, an unsatisfiable set yields the empty range, and ``===``
        specifiers contribute literal-string admission.
        """
        if not specifier_set:
            result = cls.full()
        elif not specifier_set._has_arbitrary:
            result = cls._build(
                bounds=_canonical_floor(tuple(specifier_set._get_ranges()))
            )
        else:
            result = cls.full()
            for spec in specifier_set:
                if spec.operator == "===":
                    operand = cls._build(
                        bounds=(), admit=frozenset({spec.version.lower()})
                    )
                else:
                    operand = cls._build(
                        bounds=_canonical_floor(tuple(spec._to_ranges()))
                    )
                result = result.intersection(operand)

        # Each pre-release-naming specifier opts its own versions in; their union,
        # clipped to the set's bounds by _build, is the region. Clipping refolds
        # under intersection, so a set built directly equals one built by
        # intersecting its specifiers one at a time.
        region: list[Interval] = []
        if specifier_set._prereleases is None:  # a configured policy has no region
            for spec in specifier_set:
                # ``===`` literals are not a range; filter force-admits them.
                if spec.operator != "===" and spec.prereleases:
                    spec_bounds = _canonical_floor(tuple(spec._to_ranges()))
                    region = _union_ranges(region, spec_bounds)

        return result._with_policy(
            pre_region=tuple(region),
            configured=specifier_set._prereleases,
        )

    @property
    def is_empty(self) -> bool:
        """``True`` if no version or string satisfies this range.

        Agrees with :meth:`~packaging.specifiers.SpecifierSet.is_unsatisfiable`,
        including the pre-release policy: a range whose only members are
        pre-releases is empty when that policy excludes them.

        >>> SpecifierSet(">=2,<1").to_range().is_empty
        True
        >>> SpecifierSet(">=1,<2").to_range().is_empty
        False
        >>> SpecifierSet("==1.0a1", prereleases=False).to_range().is_empty
        True
        """
        # An arbitrary-string admission or a surviving ``===`` literal is a
        # member; a literal that is a pre-release is dropped when the policy is.
        if self._arbitrary_active():
            return False

        excludes_prereleases = self._prereleases_configured is False
        for literal in self._admit:
            if excludes_prereleases:
                parsed = coerce_version(literal)
                if parsed is not None and parsed.is_prerelease:
                    continue
            return False

        if not self._bounds:
            return True

        return excludes_prereleases and ranges_are_prerelease_only(self._bounds)

    def contains(
        self,
        item: Version | str,
        prereleases: bool | None = None,
        installed: bool | None = None,
    ) -> bool:
        """Return whether item is contained in this range.

        :param item: a version string or :class:`~packaging.version.Version`.
        :param prereleases: whether to match pre-releases. ``None`` (default)
            uses the range's own policy.
        :param installed: when ``True``, accept a pre-release item even if the
            range would not otherwise allow it.

        Unlike :meth:`filter`, this does not consult the autodetected pre-release
        opt-in region; it reads only the configured policy. This mirrors
        :meth:`~packaging.specifiers.SpecifierSet.contains` versus
        :meth:`~packaging.specifiers.SpecifierSet.filter`.

        Unparsable strings do not match, except where the full
        ``SpecifierSet`` would also match: the full range admits any string,
        and a ``===`` range admits items equal to the literal
        case-insensitively.

        >>> r = SpecifierSet(">=1.0,<2.0").to_range()
        >>> r.contains("1.5")
        True
        >>> r.contains("2.0")
        False

        :raises TypeError: if item is not a str or Version.
        """
        if not isinstance(item, (str, Version)):
            raise TypeError(
                f"VersionRange.contains() expected str or Version, "
                f"got {type(item).__name__}"
            )

        parsed: Version | None = item if isinstance(item, Version) else None
        if installed and parsed is None:
            parsed = coerce_version(item)
        if installed and parsed is not None and parsed.is_prerelease:
            prereleases = True

        effective_pre = (
            self._prereleases_configured if prereleases is None else prereleases
        )

        if self._admit or self._reject:
            item_str = str(item).lower()
            if item_str in self._reject:
                return False
            if item_str in self._admit:
                if effective_pre is False:
                    literal_parsed = coerce_version(item_str)
                    if literal_parsed is not None and literal_parsed.is_prerelease:
                        return False
                return True

        if not isinstance(item, Version):
            if parsed is None:
                parsed = coerce_version(item)
            if parsed is None:
                return self._arbitrary_active()
            item = parsed

        if effective_pre is False and item.is_prerelease:
            return False
        return matches_bounds_only(self._bounds, item)

    def __contains__(self, item: Version | str) -> bool:
        """Return whether item is contained in this range.

        Forwards to :meth:`contains` with default arguments.

        >>> "1.5" in SpecifierSet(">=1.0,<2.0").to_range()
        True
        """
        return self.contains(item)

    def __eq__(self, other: object) -> bool:
        """Structural equality.

        Compares the bounds, the ``===`` admit/reject literals, the
        arbitrary-string flag, the configured pre-release policy, and the
        opt-in region, not just the version set. Keying on the region makes
        equality a congruence (equal ranges stay equal under further operations),
        so equal implies same :meth:`contains` and :meth:`filter`, but not the
        converse: an empty range keeps the flag it was built with, so two empty
        ranges need not be equal.

        Different specifiers for the same range fold to one canonical form:

        >>> SpecifierSet(">1.0a1").to_range() == SpecifierSet(">=1.0a2.dev0").to_range()
        True

        The opt-in region is part of equality, so ``<=1.0`` (no pre-releases) and
        ``<1.0.post0.dev0`` (autodetects a ``.dev`` opt-in) cover the same
        versions yet compare unequal:

        >>> le, lt = SpecifierSet("<=1.0"), SpecifierSet("<1.0.post0.dev0")
        >>> le.to_range() == lt.to_range()
        False

        >>> r = SpecifierSet(">=1.0,<2.0").to_range()
        >>> r == SpecifierSet(">=1.0,<2.0").to_range()
        True
        """
        if not isinstance(other, VersionRange):
            return NotImplemented
        return (
            self._bounds == other._bounds
            and self._admit == other._admit
            and self._reject == other._reject
            and self._admit_arbitrary == other._admit_arbitrary
            and self._prereleases_configured == other._prereleases_configured
            and self._pre_region == other._pre_region
        )

    def __hash__(self) -> int:
        return hash(
            (
                self._bounds,
                self._admit,
                self._reject,
                self._admit_arbitrary,
                self._prereleases_configured,
                self._pre_region,
            )
        )

    def __repr__(self) -> str:
        """Human-readable representation for debugging.

        >>> SpecifierSet(">=1.0,<2.0").to_range()
        <VersionRange '[1.0, 2.0.dev0)'>
        >>> SpecifierSet("").to_range()
        <VersionRange '(-inf, +inf)' arbitrary>
        >>> SpecifierSet(">=2.0,<1.0").to_range()
        <VersionRange '(empty)'>
        """
        # Body: the bounds and any ``===``-admitted literals.
        parts: list[str] = []
        if self._bounds:
            parts.append(_format_intervals(self._bounds))
        if self._admit:
            parts.append("{" + ", ".join(sorted(self._admit)) + "}")
        body = " | ".join(parts) if parts else "(empty)"

        # Rejected literals subtract from the body.
        if self._reject:
            body = f"{body} \\ {{{', '.join(sorted(self._reject))}}}"

        # Tail: the policy flags carried alongside the version set.
        tail = ""
        if self._admit_arbitrary:
            tail += " arbitrary"
        if self._prereleases_configured is not None:
            tail += f" pre={self._prereleases_configured}"
        if self._pre_region:
            tail += f" pre-region={_format_intervals(self._pre_region)!r}"

        return f"<{self.__class__.__name__} {body!r}{tail}>"
