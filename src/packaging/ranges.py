# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.
"""Public :class:`VersionRange` API.

The :class:`VersionRange` class exposes a set-algebra view of the
versions accepted by a :class:`~packaging.specifiers.Specifier` or
:class:`~packaging.specifiers.SpecifierSet`. Bound primitives, range
algebra, and the spec-to-bounds dispatch live in
:mod:`packaging._range_utils`; this module composes them into the
public class plus the
:meth:`~packaging.ranges.VersionRange.to_specifier_set` encoders,
``__repr__``, and pickle helpers that only :class:`VersionRange`
itself uses.

.. testsetup::

    from packaging.ranges import VersionRange
    from packaging.specifiers import Specifier, SpecifierSet
    from packaging.version import Version
"""

from __future__ import annotations

import typing
from typing import (
    TYPE_CHECKING,
    Any,
    Final,
    Union,
)

from ._range_utils import (
    FULL_RANGE,
    NEG_INF,
    POS_INF,
    BoundaryKind,
    BoundaryVersion,
    LowerBound,
    UpperBound,
    bound_match_string,
    bounds_for_spec,
    filter_by_ranges,
    intersect_ranges,
    matches_bounds_only,
    range_is_empty,
)
from ._version_utils import coerce_version
from .version import InvalidVersion, Version

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator, Sequence

    from ._range_utils import Interval
    from .specifiers import Specifier, SpecifierSet


__all__ = ["VersionRange"]


def __dir__() -> list[str]:
    return __all__


#: Packed pickle form of a single bound: ``(version_str_or_None,
#: inclusive, kind_or_None)``. Uses only strings, bools, and ``None``
#: so the format stays stable across packaging releases.
_PackedBound = tuple[Union[str, None], bool, Union[str, None]]

#: Cached empty frozenset for :meth:`VersionRange._build_simple` to
#: assign to ``_admit`` / ``_reject``; saves a frozenset construction
#: on every cold-path range build.
_EMPTY_FROZENSET: Final[frozenset[str]] = frozenset()


def _union_ranges(
    left: Sequence[Interval],
    right: Sequence[Interval],
) -> list[Interval]:
    """Union two sorted, non-overlapping range lists.

    Linear merge over the two pre-sorted inputs followed by a single
    coalescing pass: adjacent or overlapping ranges collapse so the
    result is itself sorted and non-overlapping.
    """
    if not left:
        return list(right)
    if not right:
        return list(left)

    # Merge two sorted lists by lower bound (linear, no resort).
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

        # Adjacent ranges merge when the previous upper sits at or past
        # the new lower; +inf/-inf short-circuits collapse the
        # unbounded cases.
        if prev_upper.version is None:
            overlaps = True
        elif lower.version is None:
            overlaps = True  # pragma: no cover (merged_input sorted by lower)
        elif prev_upper.version > lower.version:
            overlaps = True
        elif prev_upper.version == lower.version:
            overlaps = prev_upper.inclusive or lower.inclusive
        else:
            overlaps = False

        if overlaps:
            new_upper = max(prev_upper, upper)
            merged[-1] = (prev_lower, new_upper)
        else:
            merged.append((lower, upper))

    return merged


def _complement_ranges(
    ranges: Sequence[Interval],
) -> list[Interval]:
    """Complement a sorted, non-overlapping range list.

    Yields the gaps between ranges plus a leading gap before the first
    range and a trailing gap after the last. Bound inclusivity flips
    so complement-of-complement round-trips back to the input.
    """
    if not ranges:
        return list(FULL_RANGE)

    result: list[Interval] = []
    prev_upper: UpperBound | None = None

    for lower, upper in ranges:
        if prev_upper is None:
            # Leading gap from -inf up to the first range's lower.
            if lower.version is not None:
                gap_upper = UpperBound(lower.version, inclusive=not lower.inclusive)
                result.append((NEG_INF, gap_upper))
        else:
            gap_lower = LowerBound(
                prev_upper.version, inclusive=not prev_upper.inclusive
            )
            gap_upper = UpperBound(lower.version, inclusive=not lower.inclusive)
            # Adjacent ranges in the input are non-touching by
            # construction, so the gap between them is non-empty.
            if not range_is_empty(gap_lower, gap_upper):  # pragma: no branch
                result.append((gap_lower, gap_upper))
        prev_upper = upper

    # Trailing gap from the final range's upper to +inf.
    if prev_upper is not None and prev_upper.version is not None:
        gap_lower = LowerBound(prev_upper.version, inclusive=not prev_upper.inclusive)
        result.append((gap_lower, POS_INF))

    return result


def _lowest_release_at_or_above(
    value: Version | BoundaryVersion | None,
) -> Version | None:
    """Smallest non-pre-release version at or above *value*, or None."""
    if value is None:
        return None
    if isinstance(value, BoundaryVersion):
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


def _ranges_are_prerelease_only(ranges: Sequence[Interval]) -> bool:
    """``True`` when every range in *ranges* contains only pre-releases.

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


def _format_lower(bound: LowerBound) -> str:
    if bound.version is None:
        return "(-inf"
    bracket = "[" if bound.inclusive else "("
    inner = (
        bound.version.version
        if isinstance(bound.version, BoundaryVersion)
        else bound.version
    )
    return f"{bracket}{inner}"


def _format_upper(bound: UpperBound) -> str:
    if bound.version is None:
        return "+inf)"
    bracket = "]" if bound.inclusive else ")"
    inner = (
        bound.version.version
        if isinstance(bound.version, BoundaryVersion)
        else bound.version
    )
    return f"{inner}{bracket}"


def _pack_bound(bound: LowerBound | UpperBound) -> _PackedBound:
    """Serialize a bound to a primitive triple. See _PackedBound."""
    bound_version = bound.version
    if bound_version is None:
        return (None, bound.inclusive, None)
    if isinstance(bound_version, BoundaryVersion):
        return (str(bound_version.version), bound.inclusive, bound_version.kind.name)
    return (str(bound_version), bound.inclusive, None)


def _unpack_bound(
    cls: type[LowerBound | UpperBound],
    packed: _PackedBound,
) -> LowerBound | UpperBound:
    """Reverse of _pack_bound."""
    version_str, inclusive, kind_name = packed
    if version_str is None:
        return cls(None, inclusive)
    base = Version(version_str)
    if kind_name is not None:
        return cls(BoundaryVersion(base, BoundaryKind[kind_name]), inclusive)
    return cls(base, inclusive)


def _restore_version_range(
    packed_bounds: tuple[tuple[_PackedBound, _PackedBound], ...],
    arbitrary: str | None = None,
    admit: tuple[str, ...] | None = None,
    reject: tuple[str, ...] | None = None,
) -> VersionRange:
    """Pickle restorer; bypasses the ``__new__`` guard via ``_build``.

    The ``arbitrary`` arg is the pre-admit/reject slot from earlier
    betas. New pickles pass ``admit`` and ``reject`` instead. The
    matched set is preserved either way.
    """
    bounds = tuple(
        (
            typing.cast("LowerBound", _unpack_bound(LowerBound, lower)),
            typing.cast("UpperBound", _unpack_bound(UpperBound, upper)),
        )
        for lower, upper in packed_bounds
    )
    if admit is not None or reject is not None:
        return VersionRange._build(
            bounds,
            admit=frozenset(admit or ()),
            reject=frozenset(reject or ()),
        )
    if arbitrary is None:
        return VersionRange._build(bounds)
    # Legacy ``arbitrary`` matched ``{arbitrary}`` if the literal was
    # in bounds, empty otherwise.
    literal_lower = arbitrary.lower()
    legacy_range = VersionRange._build(bounds)
    if literal_lower in legacy_range:
        return VersionRange._build((), admit=frozenset({literal_lower}))
    return VersionRange._build(())


# VersionRange to SpecifierSet conversion is partial: not every range
# has a SpecifierSet form. Examples that have no single specifier:
# - PEP 440 ``<V`` excludes pre-releases of V, so the mathematical
#   complement of ``>=V`` (which keeps those pre-releases) has no
#   single specifier.
# - PEP 440 ``==V`` matches ``V+local`` too, so the strict singleton
#   ``[V, V]`` produced by :meth:`VersionRange.singleton` has none.
# - Disjoint unions whose gap is not a complete ``==V.*`` family or a
#   ``==V`` family cannot be expressed as ``base & !=...``.


def _is_dev0_version(v: Version) -> bool:
    """``True`` when *v* is exactly ``X[.Y]*.dev0``: the form ``<X`` produces."""
    return v.dev == 0 and v.pre is None and v.post is None and v.local is None


class _NotEncodable:
    """Sentinel for "this bound has no PEP 440 specifier representation"."""

    __slots__ = ()


_NOT_ENCODABLE: Final = _NotEncodable()


def _encode_lower(lower: LowerBound) -> list[str] | _NotEncodable:
    """Encode a lower bound as a list of specifier fragments.

    ``[]`` for ``-inf``, one or more fragments otherwise, or
    ``_NOT_ENCODABLE`` when the shape has no specifier form.
    AFTER_LOCALS lower bounds emit two fragments (``>=V`` plus
    ``!=V``) since the boundary excludes V and every V+local.
    """
    lower_version = lower.version
    if lower_version is None:
        return []
    if isinstance(lower_version, BoundaryVersion):
        if lower_version.kind == BoundaryKind.AFTER_POSTS and not lower.inclusive:
            return [f">{lower_version.version}"]
        if lower_version.kind == BoundaryKind.AFTER_LOCALS:
            # Strictly above V's local family. ``>=V,!=V`` produces
            # ``[V, +inf)`` minus ``[V, AFTER_LOCALS(V)]``, leaving
            # ``(AFTER_LOCALS(V), +inf)``.
            return [f">={lower_version.version}", f"!={lower_version.version}"]
        # AFTER_POSTS lower with inclusive=True is unreachable from
        # any specifier or set-algebra operation; defensive guard.
        return _NOT_ENCODABLE  # pragma: no cover
    if lower.inclusive:
        return [f">={lower_version}"]
    return _NOT_ENCODABLE


def _encode_upper(upper: UpperBound) -> list[str] | _NotEncodable:
    """Encode an upper bound as a list of specifier fragments.

    ``[]`` for ``+inf``, one or more fragments otherwise, or
    ``_NOT_ENCODABLE`` when the shape has no specifier form.
    """
    upper_version = upper.version
    if upper_version is None:
        return []
    if isinstance(upper_version, BoundaryVersion):
        if upper_version.kind == BoundaryKind.AFTER_LOCALS and upper.inclusive:
            return [f"<={upper_version.version}"]
        return _NOT_ENCODABLE
    if not upper.inclusive:
        if _is_dev0_version(upper_version):
            # <V produces upper = V.dev0 (excl); strip the synthetic
            # dev0 to recover the original V.
            return [f"<{upper_version.__replace__(dev=None)}"]
        # V (excl) upper: strictly less than V cmpkey-wise, including
        # V's pre-releases. <=V,!=V produces (-inf, AFTER_LOCALS(V)]
        # minus [V, AFTER_LOCALS(V)], leaving (-inf, V (excl)).
        return [f"<={upper_version}", f"!={upper_version}"]
    return _NOT_ENCODABLE


def _encode_interval(
    lower: LowerBound,
    upper: UpperBound,
) -> list[str] | None:
    """Encode one interval as a list of specifier fragments, or ``None``.

    Special-cases ``[V, V]`` (singleton interval) when V carries a
    local segment: ``==V+local`` matches only that literal, so the
    interval round-trips. Without a local, no specifier form exists
    (``==V`` is wider since it also matches ``V+local``).
    """
    if (
        lower.version is not None
        and upper.version is not None
        and not isinstance(lower.version, BoundaryVersion)
        and not isinstance(upper.version, BoundaryVersion)
        and lower.inclusive
        and upper.inclusive
        and lower.version == upper.version
        and lower.version.local is not None
    ):
        return [f"=={lower.version}"]
    lower_parts = _encode_lower(lower)
    if isinstance(lower_parts, _NotEncodable):
        return None
    upper_parts = _encode_upper(upper)
    if isinstance(upper_parts, _NotEncodable):
        return None
    return lower_parts + upper_parts


def _detect_not_equal(
    left_upper: UpperBound,
    right_lower: LowerBound,
) -> Version | None:
    """If the gap between two intervals is an ``!=V`` exclusion, return V.

    Two gap shapes encode as ``!=V``:

    - ``[..., V (excl)] [AFTER_LOCALS(V) (excl), ...]`` -- ``!=V`` for a
      *V* with no local segment; the gap spans V and its whole local
      family, exactly what ``==V`` (and thus ``!=V``) covers.
    - ``[..., V+local (excl)] [V+local (excl), ...]`` -- ``!=V+local``;
      the gap is the single point ``V+local``, which ``==V+local``
      matches verbatim. A no-local single point (a strict singleton's
      complement) has no ``!=`` form, so *V* must carry a local segment.
    """
    if isinstance(left_upper.version, BoundaryVersion):
        return None
    if left_upper.version is None or left_upper.inclusive:
        return None
    if not isinstance(right_lower.version, BoundaryVersion):
        # Single-point ``!=V+local`` gap: same exclusive bound on both
        # sides, and V carries a local. An inclusive right lower would
        # leave no gap; a no-local point has no ``!=`` form.
        if (
            right_lower.version is not None
            and not right_lower.inclusive
            and right_lower.version == left_upper.version
            and left_upper.version.local is not None
        ):
            return left_upper.version
        return None
    if right_lower.version.kind != BoundaryKind.AFTER_LOCALS:
        return None
    if right_lower.inclusive:
        # AFTER_LOCALS lower with inclusive=True does not arise from
        # any specifier or set-algebra operation; defensive guard.
        return None  # pragma: no cover
    if right_lower.version.version != left_upper.version:
        # The ``!=V`` pattern is contiguous; mismatched V means a union
        # of unrelated ranges. Defensive.
        return None  # pragma: no cover
    return left_upper.version


def _detect_not_equal_wildcard(
    left_upper: UpperBound,
    right_lower: LowerBound,
) -> Version | None:
    """If ``[..., V.dev0 (excl)] [V_next.dev0 (incl), ...]`` matches, return V.

    The gap shape ``!=V.*`` produces. ``V`` and ``V_next`` share an
    epoch and a release prefix differing only in the final component
    being incremented by one. Returns the prefix version (without the
    synthetic ``.dev0``) so the caller can write ``!=V.*``.
    """
    left_upper_v = left_upper.version
    right_lower_v = right_lower.version
    if isinstance(left_upper_v, BoundaryVersion) or isinstance(
        right_lower_v, BoundaryVersion
    ):
        return None
    if left_upper_v is None or right_lower_v is None:
        # First-interval upper or last-interval lower at infinity means
        # the interval is the universe and no second interval exists.
        return None  # pragma: no cover
    if left_upper.inclusive or not right_lower.inclusive:
        return None
    if not (_is_dev0_version(left_upper_v) and _is_dev0_version(right_lower_v)):
        return None
    if left_upper_v.epoch != right_lower_v.epoch:
        return None
    left_release = left_upper_v.release
    right_release = right_lower_v.release
    if len(left_release) != len(right_release) or not left_release:
        return None
    # All components except the last must match; the last increments by 1.
    if left_release[:-1] != right_release[:-1]:
        return None
    if right_release[-1] != left_release[-1] + 1:
        return None
    return left_upper_v.__replace__(dev=None)


def _encode_grouped(bounds: list[Interval]) -> list[list[str]] | None:
    """Split *bounds* into disjoint groups, encoding each as fragments.

    Consecutive intervals whose gap is an ``!=V`` / ``!=V+local`` /
    ``!=V.*`` exclusion stay in one group, with that exclusion recorded
    as an ``!=`` fragment; any other gap starts a new group. Each group
    encodes as ``_encode_interval`` of its outer bounds plus its ``!=``
    fragments. Returns one fragment list per group, or ``None`` if any
    group's outer interval has no PEP 440 form.
    """
    groups: list[list[str]] = []
    group_lower, group_upper = bounds[0]
    exclusions: list[str] = []
    for next_lower, next_upper in bounds[1:]:
        not_equal = _detect_not_equal(group_upper, next_lower)
        not_equal_wildcard = _detect_not_equal_wildcard(group_upper, next_lower)
        if not_equal is not None:
            exclusions.append(f"!={not_equal}")
        elif not_equal_wildcard is not None:
            exclusions.append(f"!={not_equal_wildcard}.*")
        else:
            # A non-``!=`` gap closes the current group and opens a new one.
            outer = _encode_interval(group_lower, group_upper)
            if outer is None:
                return None
            groups.append(outer + exclusions)
            group_lower, exclusions = next_lower, []
        group_upper = next_upper

    outer = _encode_interval(group_lower, group_upper)
    if outer is None:
        return None
    groups.append(outer + exclusions)
    return groups


class VersionRange:
    """A set of :class:`~packaging.version.Version` values, expressed as
    a union of disjoint intervals on the PEP 440 version ordering.

    Construct with :meth:`from_specifier` / :meth:`from_specifier_set`,
    or via :meth:`~packaging.specifiers.Specifier.to_range` /
    :meth:`~packaging.specifiers.SpecifierSet.to_range`.
    Compose with :meth:`intersection`, :meth:`union`, :meth:`complement`
    (and the ``&`` / ``|`` / ``~`` operator aliases).

    >>> r = VersionRange.from_specifier_set(SpecifierSet(">=1.0,<2.0"))
    >>> "1.5" in r
    True
    >>> "2.0" in r
    False
    >>> bool(VersionRange.from_specifier_set(SpecifierSet(">=2.0,<1.0")))
    False

    PEP 440's ``===`` operator matches a candidate string verbatim
    (case-insensitive) rather than a set of
    :class:`~packaging.version.Version` values.
    Ranges built from ``===`` specifiers still support membership,
    set operations, and conversion back to a
    :class:`~packaging.specifiers.SpecifierSet`;
    matching follows the literal-equality rule instead of the
    version-ordering rule.
    """

    __slots__ = ("_admit", "_bounds", "_is_simple", "_reject")
    _bounds: tuple[Interval, ...]
    #: Whether :meth:`filter` can dispatch straight to the bounds-only
    #: filter: no admit/reject literals and bounds aren't the full range.
    _is_simple: bool
    #: Case-folded strings the range admits in addition to its bounds.
    #: ``===wat`` produces ``_admit = {"wat"}``.
    _admit: frozenset[str]
    #: Case-folded strings the range rejects. Overrides ``_admit`` and
    #: ``_bounds``. Populated by :meth:`complement` of a range whose
    #: ``_admit`` was non-empty.
    _reject: frozenset[str]

    def __new__(cls, *args: object, **kwargs: object) -> VersionRange:  # noqa: PYI034
        raise TypeError(
            "cannot create 'VersionRange' instances directly; use "
            "VersionRange.from_specifier(), "
            "VersionRange.from_specifier_set(), "
            "Specifier.to_range(), or SpecifierSet.to_range() instead"
        )

    @classmethod
    def _build(
        cls,
        bounds: tuple[Interval, ...],
        admit: frozenset[str] = frozenset(),
        reject: frozenset[str] = frozenset(),
    ) -> VersionRange:
        """Internal factory; bypasses :meth:`__new__`.

        Drops admit literals already covered by bounds and reject
        literals already outside bounds. Reject wins over admit on
        overlap.
        """
        if admit and reject:
            admit = admit - reject
        if admit:
            admit = frozenset(s for s in admit if not bound_match_string(bounds, s))
        if reject:
            reject = frozenset(s for s in reject if bound_match_string(bounds, s))
        instance = object.__new__(cls)
        instance._bounds = bounds
        instance._admit = admit
        instance._reject = reject
        # Pure-bound range: filter can skip the admission dispatch.
        instance._is_simple = not admit and not reject and bounds != FULL_RANGE
        return instance

    @classmethod
    def _build_simple(cls, bounds: tuple[Interval, ...]) -> VersionRange:
        """Internal fast factory for ranges with no admit/reject literals.

        Equivalent to ``cls._build(bounds)`` when both literal sets are
        empty; skips the (empty) literal-handling branches that dominate
        cold-path overhead for specifiers built from PEP 440 operators.
        """
        instance = object.__new__(cls)
        instance._bounds = bounds
        instance._admit = _EMPTY_FROZENSET
        instance._reject = _EMPTY_FROZENSET
        instance._is_simple = bounds != FULL_RANGE
        return instance

    def _has_literals(self) -> bool:
        """``True`` when ``_admit`` or ``_reject`` is non-empty."""
        return bool(self._admit) or bool(self._reject)

    @classmethod
    def empty(cls) -> VersionRange:
        """Return the empty range. No version satisfies it.

        >>> VersionRange.empty().is_empty
        True
        >>> "1.0" in VersionRange.empty()
        False
        """
        return cls._build(())

    @classmethod
    def full(cls) -> VersionRange:
        """Return the full range. Every PEP 440 version satisfies it.

        >>> "1.0" in VersionRange.full()
        True
        >>> VersionRange.full().is_empty
        False
        """
        return cls._build(FULL_RANGE)

    @classmethod
    def singleton(cls, version: Version | str) -> VersionRange:
        """Return the range that contains only *version*.

        >>> r = VersionRange.singleton("1.2.3")
        >>> "1.2.3" in r
        True
        >>> "1.2.4" in r
        False

        :raises packaging.version.InvalidVersion: if *version* is a
            string that does not parse as a PEP 440 version.
        """
        if not isinstance(version, Version):
            version = Version(version)
        lower = LowerBound(version, inclusive=True)
        upper = UpperBound(version, inclusive=True)
        return cls._build(((lower, upper),))

    def intersection(self, other: VersionRange) -> VersionRange:
        """Range containing exactly the versions in both *self* and *other*.

        >>> a = VersionRange.from_specifier_set(SpecifierSet(">=1.0"))
        >>> b = VersionRange.from_specifier_set(SpecifierSet("<2.0"))
        >>> ab = VersionRange.from_specifier_set(SpecifierSet(">=1.0,<2.0"))
        >>> a.intersection(b) == ab
        True
        """
        if not self._has_literals() and not other._has_literals():
            return self._build(tuple(intersect_ranges(self._bounds, other._bounds)))
        new_bounds = tuple(intersect_ranges(self._bounds, other._bounds))
        return self._combine_literals(other, new_bounds, intersect=True)

    def union(self, other: VersionRange) -> VersionRange:
        """Range containing every version in *self* or *other*.

        >>> a = VersionRange.singleton("1.0")
        >>> b = VersionRange.singleton("2.0")
        >>> "1.0" in a.union(b) and "2.0" in a.union(b)
        True
        >>> "1.5" in a.union(b)
        False
        """
        if not self._has_literals() and not other._has_literals():
            return self._build(tuple(_union_ranges(self._bounds, other._bounds)))
        new_bounds = tuple(_union_ranges(self._bounds, other._bounds))
        return self._combine_literals(other, new_bounds, intersect=False)

    def complement(self) -> VersionRange:
        """Range containing every version *not* in *self*.

        >>> r = VersionRange.from_specifier(Specifier(">=1.0"))
        >>> "0.5" in r.complement()
        True
        >>> "1.5" in r.complement()
        False
        >>> r.complement().complement() == r
        True
        """
        if not self._has_literals():
            return self._build(tuple(_complement_ranges(self._bounds)))
        # Swap the admit and reject sets, complement the bounds.
        # ``_build`` drops anything now redundant against the new bounds.
        return self._build(
            tuple(_complement_ranges(self._bounds)),
            admit=self._reject,
            reject=self._admit,
        )

    def _combine_literals(
        self,
        other: VersionRange,
        new_bounds: tuple[Interval, ...],
        *,
        intersect: bool,
    ) -> VersionRange:
        """Resolve admit/reject for ``self & other`` or ``self | other``.

        The bound-only result is already in *new_bounds*. For each
        literal seen on either side, decide whether the combined
        predicate (AND for intersection, OR for union) admits it, then
        record an explicit admit or reject when the new bounds would
        give the wrong answer on their own.
        """
        admits: set[str] = set()
        rejects: set[str] = set()
        for literal in self._admit | self._reject | other._admit | other._reject:
            self_in = self._matches_literal(literal)
            other_in = other._matches_literal(literal)
            want = (self_in and other_in) if intersect else (self_in or other_in)
            bound_in = bound_match_string(new_bounds, literal)
            if want and not bound_in:
                admits.add(literal)
            elif not want and bound_in:
                rejects.add(literal)
        return self._build(
            new_bounds, admit=frozenset(admits), reject=frozenset(rejects)
        )

    def _matches_literal(self, literal: str) -> bool:
        """Whether *literal* (case-folded) matches this range's predicate."""
        if literal in self._reject:
            return False
        if literal in self._admit:
            return True
        return bound_match_string(self._bounds, literal)

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

    def filter(
        self,
        iterable: Iterable[Any],
        key: Callable[[Any], Version | str] | None = None,
        prereleases: bool | None = None,
    ) -> Iterator[Any]:
        """Yield items from *iterable* whose version falls inside the range.

        With *prereleases* ``None`` the PEP 440 default applies:
        pre-releases are buffered and only emitted if no final release
        in *iterable* is in range.

        Filtering matches
        :meth:`~packaging.specifiers.SpecifierSet.filter` for the same
        :class:`~packaging.specifiers.Specifier` /
        :class:`~packaging.specifiers.SpecifierSet`, including the
        admission of unparsable strings for the empty ``SpecifierSet("")``
        and the case-insensitive literal match for ``===``.

        >>> r = VersionRange.from_specifier_set(SpecifierSet(">=1.0,<2.0"))
        >>> list(r.filter(["0.9", "1.5", "2.0"]))
        ['1.5']
        """
        if self._is_simple:
            return filter_by_ranges(self._bounds, iterable, key, prereleases)
        return self._filter_with_admission(iterable, key, prereleases)

    def _filter_with_admission(
        self,
        iterable: Iterable[Any],
        key: Callable[[Any], Version | str] | None,
        prereleases: bool | None,
    ) -> Iterator[Any]:
        """Filter for ranges that admit unparsable strings.

        Used by ``===`` ranges (literal admit/reject) and the full-range
        carve-out. Same PEP 440 pre-release buffering for both, with a
        different admission check.
        """
        admit_set = self._admit
        reject_set = self._reject
        full_bounds = self._bounds == FULL_RANGE

        def admit(item: Any) -> tuple[bool, Version | None]:  # noqa: ANN401
            raw: Version | str = item if key is None else key(item)
            raw_lower = str(raw).lower()
            if reject_set and raw_lower in reject_set:
                return False, None
            if admit_set and raw_lower in admit_set:
                return True, coerce_version(raw)
            parsed = coerce_version(raw)
            if parsed is None:
                return full_bounds, None
            if not full_bounds and not self._matches_bounds(parsed):
                return False, None
            return True, parsed

        if prereleases is True:
            for item in iterable:
                ok, _ = admit(item)
                if ok:
                    yield item
            return

        if prereleases is False:
            for item in iterable:
                ok, parsed = admit(item)
                if not ok:
                    continue
                if parsed is not None and parsed.is_prerelease:
                    continue
                yield item
            return

        # PEP 440 default: yield finals immediately; buffer the rest
        # until we know whether any final exists.
        all_nonfinal: list[Any] = []
        arbitrary_strings: list[Any] = []
        found_final = False
        for item in iterable:
            ok, parsed = admit(item)
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
            if not found_final:
                all_nonfinal.append(item)
        if not found_final:
            yield from all_nonfinal

    @classmethod
    def from_specifier(cls, specifier: Specifier) -> VersionRange:
        """Return the :class:`VersionRange` accepted by *specifier*.

        >>> isinstance(VersionRange.from_specifier(Specifier(">=1.0")), VersionRange)
        True
        """
        op = specifier.operator
        ver = specifier.version
        if op == "===":
            return cls._build(bounds=(), admit=frozenset({ver.lower()}))

        return cls._build_simple(bounds=bounds_for_spec(op, ver))

    @classmethod
    def from_specifier_set(cls, specifier_set: SpecifierSet) -> VersionRange:
        """Return the :class:`VersionRange` accepted by *specifier_set*.

        The intersection of every specifier in the set. An empty
        :class:`~packaging.specifiers.SpecifierSet` yields the
        unbounded range; an unsatisfiable set yields an empty
        :class:`VersionRange`. To reuse the result, call
        :meth:`~packaging.specifiers.SpecifierSet.to_range`, which
        caches it on the instance.

        >>> isinstance(
        ...     VersionRange.from_specifier_set(SpecifierSet(">=1.0,<2.0")),
        ...     VersionRange,
        ... )
        True
        >>> VersionRange.from_specifier_set(SpecifierSet(">=2.0,<1.0")).is_empty
        True
        """
        # Intersect every specifier through the public API. ``&`` and
        # :meth:`from_specifier` already handle ``===`` literals via the
        # admit set, so the fold needs no operator-specific special
        # cases. An empty set leaves the unbounded ``full()``.
        result = cls.full()
        for spec in specifier_set:
            result = result.intersection(cls.from_specifier(spec))
        return result

    def to_specifier_set(self) -> SpecifierSet | None:
        """Return a single
        :class:`~packaging.specifiers.SpecifierSet` whose
        :meth:`from_specifier_set` yields *self*, or ``None`` if no
        such set exists.

        :class:`~packaging.specifiers.SpecifierSet` cannot express every
        range. PEP 440's
        operator set has no syntax for the strict singleton ``{V}`` or
        for the bounds produced by complementing ``>V``; for those
        ranges the result is ``None``. Use :meth:`to_specifier_sets`
        when a tuple of specifier sets is acceptable. The empty range
        maps to the range ``SpecifierSet("<0")`` (``<0`` excludes
        ``0.dev0``, the smallest PEP 440 version); the full range maps
        to the empty ``SpecifierSet("")``.

        >>> r = VersionRange.from_specifier_set(SpecifierSet(">=1.0,<2.0"))
        >>> str(r.to_specifier_set())
        '<2.0,>=1.0'
        >>> VersionRange.singleton("1.5").to_specifier_set() is None
        True
        """
        # Local import avoids the circular .specifiers <-> .ranges load.
        from .specifiers import SpecifierSet  # noqa: PLC0415

        if self._reject:
            # No PEP 440 operator excludes a literal string while
            # admitting other versions.
            return None
        if self._admit:
            return self._admit_to_specifier_set()
        if self.is_empty:
            # ``<0`` parses to upper = 0.dev0 (excl), the smallest
            # possible PEP 440 version, so the range contains nothing.
            return SpecifierSet("<0")
        if self._bounds == FULL_RANGE:
            return SpecifierSet("")

        # A single SpecifierSet exists only when every interval joins
        # into one ``!=``-connected group; a genuine disjoint gap (more
        # than one group) has no single-set form.
        groups = _encode_grouped(list(self._bounds))
        if groups is None or len(groups) != 1:
            return None
        return SpecifierSet(",".join(groups[0]))

    def to_specifier_sets(self) -> tuple[SpecifierSet, ...] | None:
        """Return a tuple of
        :class:`~packaging.specifiers.SpecifierSet` whose union equals
        *self*, or ``None`` if no such tuple exists.

        Looser than :meth:`to_specifier_set`: each maximal run of
        intervals joined by ``!=V`` / ``!=V.*`` gaps becomes one
        :class:`~packaging.specifiers.SpecifierSet`, and genuinely
        disjoint runs become separate ones. ``None`` only when some
        run's outer interval has no PEP 440 form (for example the
        strict singleton produced by :meth:`singleton`).

        >>> r = (
        ...     VersionRange.from_specifier_set(SpecifierSet(">=1.0,<2.0"))
        ...     | VersionRange.from_specifier_set(SpecifierSet(">=3.0,<4.0"))
        ... )
        >>> [str(s) for s in r.to_specifier_sets()]
        ['<2.0,>=1.0', '<4.0,>=3.0']
        >>> VersionRange.singleton("1.5").to_specifier_sets() is None
        True
        """
        from .specifiers import SpecifierSet  # noqa: PLC0415

        if self._reject:
            return None
        if self._admit:
            single = self._admit_to_specifier_set()
            if single is None:
                return None
            return (single,)
        if self.is_empty:
            return (SpecifierSet("<0"),)
        if self._bounds == FULL_RANGE:
            return (SpecifierSet(""),)

        # One SpecifierSet per disjoint group; ``!=`` gaps stay merged
        # inside their group.
        groups = _encode_grouped(list(self._bounds))
        if groups is None:
            return None
        return tuple(SpecifierSet(",".join(group)) for group in groups)

    def _admit_to_specifier_set(self) -> SpecifierSet | None:
        """Encode a single ``===L`` range as ``SpecifierSet("===L")``.

        Returns ``None`` for shapes PEP 440 cannot express: multiple
        admit literals (no ``=== A or === B`` syntax), or admit
        combined with a non-empty bound set.
        """
        from .specifiers import SpecifierSet  # noqa: PLC0415

        if len(self._admit) != 1 or self._bounds:
            return None
        (literal,) = self._admit
        return SpecifierSet(f"==={literal}")

    def __reduce__(self) -> tuple[object, ...]:
        # Pickle to a primitive form (see ``_PackedBound``). The legacy
        # ``arbitrary`` slot is kept for older restorer signatures.
        return (
            _restore_version_range,
            (
                tuple(
                    (_pack_bound(lower), _pack_bound(upper))
                    for lower, upper in self._bounds
                ),
                None,
                tuple(sorted(self._admit)),
                tuple(sorted(self._reject)),
            ),
        )

    @property
    def is_empty(self) -> bool:
        """``True`` if no version or string satisfies this range.

        >>> VersionRange.from_specifier_set(SpecifierSet(">=2,<1")).is_empty
        True
        >>> VersionRange.from_specifier_set(SpecifierSet(">=1,<2")).is_empty
        False
        """
        return not self._bounds and not self._admit

    @property
    def is_prerelease_only(self) -> bool:
        """``True`` when every match is a PEP 440 pre-release.

        Used by
        :meth:`~packaging.specifiers.SpecifierSet.is_unsatisfiable` to
        detect sets
        that admit no candidate under the default ``prereleases=False``
        reading. Returns ``False`` for the empty range.

        >>> r = VersionRange.from_specifier_set(SpecifierSet(">=1.0a1,<1.0rc1"))
        >>> r.is_prerelease_only
        True
        >>> VersionRange.from_specifier(Specifier(">=1.0")).is_prerelease_only
        False
        """
        if self.is_empty:
            return False
        if self._reject:
            return False
        for literal in self._admit:
            parsed = coerce_version(literal)
            if parsed is None or not parsed.is_prerelease:
                return False
        if self._bounds:
            return _ranges_are_prerelease_only(self._bounds)
        return True

    def __bool__(self) -> bool:
        """``False`` when the range is empty, ``True`` otherwise.

        >>> bool(VersionRange.from_specifier_set(SpecifierSet(">=1,<2")))
        True
        >>> bool(VersionRange.from_specifier_set(SpecifierSet(">=2,<1")))
        False
        """
        return bool(self._bounds) or bool(self._admit)

    def __contains__(self, item: Version | str) -> bool:
        """Return whether *item* is contained in this range.

        Unparsable strings do not match, except where the full
        ``SpecifierSet`` would also match: the full range admits any
        string, and a ``===`` range admits items whose string equals
        the literal case-insensitively.

        >>> r = VersionRange.from_specifier_set(SpecifierSet(">=1.0,<2.0"))
        >>> "1.5" in r
        True
        >>> "2.0" in r
        False
        """
        if self._admit or self._reject:
            item_str = str(item).lower()
            if item_str in self._reject:
                return False
            if item_str in self._admit:
                return True
        if self._bounds == FULL_RANGE:
            # ``SpecifierSet("")`` admits any string. Match that.
            return True
        if not isinstance(item, Version):
            try:
                item = Version(item)
            except InvalidVersion:
                return False
        return self._matches_bounds(item)

    def _matches_bounds(self, item: Version) -> bool:
        """Bound-only membership check; ignores admit/reject."""
        return matches_bounds_only(self._bounds, item)

    def __eq__(self, other: object) -> bool:
        """Structural equality. Two ranges are equal when they admit
        exactly the same set of versions and strings.

        >>> a = VersionRange.from_specifier_set(SpecifierSet(">=1.0,<2.0"))
        >>> b = VersionRange.from_specifier_set(SpecifierSet(">=1.0,<2.0"))
        >>> a == b
        True
        """
        if not isinstance(other, VersionRange):
            return NotImplemented
        return (
            self._bounds == other._bounds
            and self._admit == other._admit
            and self._reject == other._reject
        )

    def __hash__(self) -> int:
        if not self._admit and not self._reject:
            return hash(self._bounds)
        return hash((self._bounds, self._admit, self._reject))

    def __repr__(self) -> str:
        """Human-readable representation. Internal layout, debugging only.

        >>> VersionRange.from_specifier_set(SpecifierSet(">=1.0,<2.0"))
        <VersionRange '[1.0, 2.0.dev0)'>
        >>> VersionRange.from_specifier_set(SpecifierSet(""))
        <VersionRange '(-inf, +inf)'>
        >>> VersionRange.from_specifier_set(SpecifierSet(">=2.0,<1.0"))
        <VersionRange '(empty)'>
        >>> VersionRange.from_specifier(Specifier("===wat"))
        <VersionRange '{wat}'>
        """
        if self._bounds:
            bound_body = " | ".join(
                f"{_format_lower(lower)}, {_format_upper(upper)}"
                for lower, upper in self._bounds
            )
        else:
            bound_body = "(empty)" if not self._admit else ""
        parts: list[str] = []
        if bound_body:
            parts.append(bound_body)
        if self._admit:
            parts.append("{" + ", ".join(sorted(self._admit)) + "}")
        body = " | ".join(parts) if parts else "(empty)"
        if self._reject:
            body = f"{body} \\ {{{', '.join(sorted(self._reject))}}}"
        return f"<{self.__class__.__name__} {body!r}>"
