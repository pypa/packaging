# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.
"""Public :class:`VersionRange` API.

A set-algebra view of the versions accepted by a
:class:`~packaging.specifiers.Specifier` or
:class:`~packaging.specifiers.SpecifierSet`. Ranges support intersection,
union, and complement; membership and filtering match the originating
specifier; and conversion back to a
:class:`~packaging.specifiers.SpecifierSet` is available where a PEP 440
form exists.

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
    TypeVar,
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
    bounds_for_spec,
    canonical_lower,
    filter_by_ranges,
    intersect_ranges,
    intersect_specifier_bounds,
    matches_bounds_only,
    range_is_empty,
    ranges_are_prerelease_only,
)
from ._version_utils import coerce_version, trim_release
from .version import InvalidVersion, Version

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator, Sequence

    from ._range_utils import Interval
    from .specifiers import Specifier, SpecifierSet


__all__ = ["VersionRange"]

# Defined locally to avoid importing from ``packaging.specifiers``, which
# imports this module. Mirrors the names of the same shape in
# :mod:`packaging.specifiers`.
T = TypeVar("T")
UnparsedVersion = Union[Version, str]
UnparsedVersionVar = TypeVar("UnparsedVersionVar", bound=UnparsedVersion)


def __dir__() -> list[str]:
    return __all__


#: Packed pickle form of a single bound: ``(version_str_or_None,
#: inclusive, kind_code_or_None)``. ``kind_code`` is the stable
#: integer code from :data:`_KIND_TO_CODE` rather than the
#: :class:`BoundaryKind` enum member's ``.name``, so renaming the enum
#: in :mod:`_range_utils` does not break cross-release pickle restore.
#: Uses only ints, strings, bools, and ``None`` so the format stays
#: stable across packaging releases.
_PackedBound = tuple[Union[str, None], bool, Union[int, None]]

#: Stable integer codes for :class:`BoundaryKind` members. ``ranges.py``
#: owns this map so the pickle format is decoupled from the enum
#: member names; never reuse a retired code, only allocate new ones.
_KIND_TO_CODE: Final[dict[BoundaryKind, int]] = {
    BoundaryKind.AFTER_LOCALS: 1,
    BoundaryKind.AFTER_POSTS: 2,
}
_CODE_TO_KIND: Final[dict[int, BoundaryKind]] = {
    code: kind for kind, code in _KIND_TO_CODE.items()
}

#: Packed pickle form of a :class:`VersionRange`: a 6-tuple of
#: ``(packed_bounds, admit, reject, admit_arbitrary, prereleases,
#: prereleases_configured)``. Built from primitives only so the format
#: stays stable across packaging releases. See
#: :meth:`VersionRange.__getstate__` and :meth:`VersionRange.__setstate__`.
_VersionRangeState = tuple[
    tuple[tuple[_PackedBound, _PackedBound], ...],
    tuple[str, ...],
    tuple[str, ...],
    bool,
    Union[bool, None],
    Union[bool, None],
]


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
            # Two ``-inf`` lowers reach here when merging two ``<V`` ranges.
            overlaps = True
        elif prev_upper.version > lower.version:
            overlaps = True
        elif prev_upper.version == lower.version:
            overlaps = prev_upper.inclusive or lower.inclusive
        else:
            # Ordering leaves a gap, but it holds no version when the two
            # bounds straddle a synthetic boundary (e.g. AFTER_LOCALS(V) up
            # to V.post0.dev0). Merge across an empty gap to stay canonical.
            gap_lower = canonical_lower(
                LowerBound(prev_upper.version, inclusive=not prev_upper.inclusive)
            )
            gap_upper = UpperBound(lower.version, inclusive=not lower.inclusive)
            overlaps = range_is_empty(gap_lower, gap_upper)

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
            gap_lower = canonical_lower(
                LowerBound(prev_upper.version, inclusive=not prev_upper.inclusive)
            )
            gap_upper = UpperBound(lower.version, inclusive=not lower.inclusive)
            # Adjacent ranges in the input are non-touching by
            # construction, so the gap between them is non-empty.
            if not range_is_empty(gap_lower, gap_upper):  # pragma: no branch
                result.append((gap_lower, gap_upper))
        prev_upper = upper

    # Trailing gap from the final range's upper to +inf. The empty-input
    # early return above guarantees the loop ran, so ``prev_upper`` is set.
    assert prev_upper is not None
    if prev_upper.version is not None:
        gap_lower = canonical_lower(
            LowerBound(prev_upper.version, inclusive=not prev_upper.inclusive)
        )
        result.append((gap_lower, POS_INF))

    return result


def _bound_version_str(value: BoundaryVersion | Version) -> str:
    """Printout for a bound's inner value, kind-tagged for boundaries.

    A bare :class:`Version` renders as itself. A :class:`BoundaryVersion`
    renders as ``V[KIND]`` so ``==1.0`` (upper is ``AFTER_LOCALS``) and
    ``singleton('1.0')`` (upper is bare ``Version``) are distinguishable
    in repr even though their inner versions match.
    """
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


def _pack_bound(bound: LowerBound | UpperBound) -> _PackedBound:
    """Serialize a bound to a primitive triple. See _PackedBound."""
    bound_version = bound.version
    if bound_version is None:
        return (None, bound.inclusive, None)
    if isinstance(bound_version, BoundaryVersion):
        return (
            str(bound_version.version),
            bound.inclusive,
            _KIND_TO_CODE[bound_version.kind],
        )
    return (str(bound_version), bound.inclusive, None)


def _unpack_inner(
    packed: _PackedBound,
) -> tuple[BoundaryVersion | Version | None, bool]:
    """Decode the (version-or-boundary, inclusive) pair from a packed bound."""
    version_str, inclusive, kind_code = packed
    if version_str is None:
        return None, inclusive
    base = Version(version_str)
    if kind_code is not None:
        kind = _CODE_TO_KIND.get(kind_code)
        if kind is None:
            raise ValueError(
                f"Unknown BoundaryKind code {kind_code!r} in packaging "
                f"VersionRange pickle state; expected one of "
                f"{sorted(_CODE_TO_KIND)}"
            )
        return BoundaryVersion(base, kind), inclusive
    return base, inclusive


def _new_version_range(cls: type[VersionRange]) -> VersionRange:
    """Pickle/copy reconstructor; bypasses the :meth:`VersionRange.__new__` guard.

    Preserves ``cls`` so subclasses round-trip with their own type. Pairs
    with :meth:`VersionRange.__setstate__` to populate the slots.
    """
    return object.__new__(cls)


def _is_dev0_version(version: Version) -> bool:
    """``True`` when version is exactly ``X[.Y]*.dev0`` (the form ``<X`` produces)."""
    return (
        version.dev == 0
        and version.pre is None
        and version.post is None
        and version.local is None
    )


def _encode_lower(lower: LowerBound) -> list[str] | None:
    """Encode a lower bound as a list of specifier fragments.

    ``[]`` for ``-inf``, one or more fragments otherwise, or ``None`` when
    the shape has no specifier form. AFTER_LOCALS lower bounds emit two
    fragments (``>=V`` plus ``!=V``) since the boundary excludes V and
    every V+local.
    """
    lower_version = lower.version
    if lower_version is None:
        return []
    if isinstance(lower_version, BoundaryVersion):
        if lower_version.kind == BoundaryKind.AFTER_POSTS and not lower.inclusive:
            return [f">{lower_version.version}"]
        if lower_version.kind == BoundaryKind.AFTER_LOCALS:
            inner = lower_version.version
            if inner.post is not None or inner.dev is not None:
                # ``>V`` already excludes only V's local family when V
                # carries post or dev (PEP 440's post-release rule does
                # not fire); a single ``>V`` fragment matches the bound.
                return [f">{inner}"]
            # Strictly above V's local family. ``>=V,!=V`` produces
            # ``[V, +inf)`` minus ``[V, AFTER_LOCALS(V)]``, leaving
            # ``(AFTER_LOCALS(V), +inf)``.
            return [f">={inner}", f"!={inner}"]
        # AFTER_POSTS lower with inclusive=True does not arise from any
        # specifier or set-algebra operation.
        return None  # pragma: no cover
    if lower.inclusive:
        return [f">={lower_version}"]
    return None


def _encode_upper(upper: UpperBound) -> list[str] | None:
    """Encode an upper bound as a list of specifier fragments.

    ``[]`` for ``+inf``, one or more fragments otherwise, or ``None`` when
    the shape has no specifier form.
    """
    upper_version = upper.version
    if upper_version is None:
        return []
    if isinstance(upper_version, BoundaryVersion):
        if upper_version.kind == BoundaryKind.AFTER_LOCALS and upper.inclusive:
            return [f"<={upper_version.version}"]
        return None
    if not upper.inclusive:
        if _is_dev0_version(upper_version):
            # <V produces upper = V.dev0 (excl); strip the synthetic
            # dev0 to recover the original V.
            return [f"<{upper_version.__replace__(dev=None)}"]

        # V (excl) upper: strictly less than V cmpkey-wise, including
        # V's pre-releases. <=V,!=V produces (-inf, AFTER_LOCALS(V)]
        # minus [V, AFTER_LOCALS(V)], leaving (-inf, V (excl)).
        return [f"<={upper_version}", f"!={upper_version}"]
    return None


def _detect_equal_wildcard(
    lower: LowerBound,
    upper: UpperBound,
) -> Version | None:
    """If ``[lower, upper)`` is the ``==V.*`` shape, return ``V``.

    Shape: inclusive ``V.dev0`` lower, exclusive ``NextV.dev0`` upper,
    same epoch, where ``NextV`` shares ``V``'s release prefix with the
    last segment incremented by one.
    """
    # Reject any shape that is not two real versions with matching
    # ``[V.dev0, W.dev0)`` brackets.
    if isinstance(lower.version, BoundaryVersion) or isinstance(
        upper.version, BoundaryVersion
    ):
        return None
    if lower.version is None or upper.version is None:
        return None
    if not lower.inclusive or upper.inclusive:
        return None
    if not (_is_dev0_version(lower.version) and _is_dev0_version(upper.version)):
        return None
    if lower.version.epoch != upper.version.epoch:
        return None

    # Normalize trailing zeros so equal versions with different release
    # tuple lengths (``Version("1")`` vs ``Version("1.0")``) compare on
    # the same footing; pad the shorter side to match the longer.
    lower_release = trim_release(lower.version.release)
    upper_release = trim_release(upper.version.release)
    padded_length = max(len(lower_release), len(upper_release))
    # ``trim_release`` always leaves at least one segment.
    assert padded_length > 0
    lower_release += (0,) * (padded_length - len(lower_release))
    upper_release += (0,) * (padded_length - len(upper_release))

    # Releases must share a prefix and differ by exactly +1 in the last
    # segment, so the upper is the next wildcard sibling of the lower.
    if lower_release[:-1] != upper_release[:-1]:
        return None
    if upper_release[-1] != lower_release[-1] + 1:
        return None

    return lower.version.__replace__(release=lower_release, dev=None)


def _encode_interval(
    lower: LowerBound,
    upper: UpperBound,
) -> list[str] | None:
    """Encode one interval as a list of specifier fragments, or ``None``.

    Special-cases ``[V, V]`` (singleton interval) when V carries a
    local segment: ``==V+local`` matches only that literal, so the
    interval round-trips. Without a local, no specifier form exists
    (``==V`` is wider since it also matches ``V+local``).

    Detects the ``==V.*`` shape so the encoded fragment carries no
    synthetic ``.dev0`` literal, keeping
    :attr:`SpecifierSet.prereleases` auto-detect aligned with the source.
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
    wildcard = _detect_equal_wildcard(lower, upper)
    if wildcard is not None:
        return [f"=={wildcard}.*"]
    lower_parts = _encode_lower(lower)
    if lower_parts is None:
        return None
    upper_parts = _encode_upper(upper)
    if upper_parts is None:
        return None
    return lower_parts + upper_parts


def _detect_not_equal(
    left_upper: UpperBound,
    right_lower: LowerBound,
) -> Version | None:
    """If the gap between two intervals is an ``!=V`` exclusion, return V.

    Two gap shapes encode as ``!=V``:

    - ``[..., V (excl)] [AFTER_LOCALS(V) (excl), ...]``: ``!=V`` for a
      V with no local segment. The gap spans V and its whole local
      family, exactly what ``==V`` (and thus ``!=V``) covers.
    - ``[..., V+local (excl)] [V+local (excl), ...]``: ``!=V+local``.
      The gap is the single point ``V+local``, which ``==V+local``
      matches verbatim. A no-local single point (a strict singleton's
      complement) has no ``!=`` form, so V must carry a local segment.
    """
    # Left upper must be an exclusive real-version bound.
    if isinstance(left_upper.version, BoundaryVersion):
        return None
    if left_upper.version is None or left_upper.inclusive:
        return None

    # Single-point ``!=V+local`` gap: same exclusive bound on both sides,
    # and V carries a local. An inclusive right lower would leave no gap;
    # a no-local point has no ``!=`` form.
    if not isinstance(right_lower.version, BoundaryVersion):
        if (
            right_lower.version is not None
            and not right_lower.inclusive
            and right_lower.version == left_upper.version
            and left_upper.version.local is not None
        ):
            return left_upper.version
        return None

    # ``!=V`` gap: AFTER_LOCALS(V) on the right, V on the left.
    if right_lower.version.kind != BoundaryKind.AFTER_LOCALS:
        return None
    if right_lower.inclusive:
        return None  # pragma: no cover
    if right_lower.version.version != left_upper.version:
        return None  # pragma: no cover

    return left_upper.version


def _filter_universal(
    iterable: Iterable[Any],
    key: Callable[[Any], Version | str] | None,
    prereleases: bool | None,
) -> Iterator[Any]:
    """Filter for the universal range (admits every item).

    Fast path for :meth:`VersionRange.filter` on ``VersionRange.full()`` and
    equivalents. Parses each item only as far as needed for the pre-release
    decision, mirroring :meth:`SpecifierSet.filter` on ``SpecifierSet("")``.
    """
    if prereleases is True:
        yield from iterable
        return

    if prereleases is False:
        for item in iterable:
            parsed = coerce_version(item if key is None else key(item))
            if parsed is None or not parsed.is_prerelease:
                yield item
        return

    # PEP 440 default: yield finals immediately. Until the first final
    # arrives, ``unparseable`` and ``nonfinal_tail`` together hold every
    # item seen so far. On the first final we release unparseables (they
    # belong before the final like SpecifierSet("") does); the pre-release
    # tail stays buffered and only comes out if no final ever arrives.
    nonfinal_tail: list[Any] = []
    unparseable: list[Any] = []
    found_final = False
    for item in iterable:
        parsed = coerce_version(item if key is None else key(item))
        if parsed is None:
            if found_final:
                yield item
            else:
                unparseable.append(item)
                nonfinal_tail.append(item)
            continue
        if not parsed.is_prerelease:
            if not found_final:
                yield from unparseable
                unparseable.clear()
                found_final = True
            yield item
            continue
        if not found_final:
            nonfinal_tail.append(item)
    if not found_final:
        yield from nonfinal_tail


def _struct_admits(
    bounds: tuple[Interval, ...], admit_arbitrary: bool, literal: str
) -> bool:
    """True when the bounds (plus arbitrary admission) admit literal.

    Skips the explicit admit/reject sets, which the caller layers on top.
    Non-version strings match via ``admit_arbitrary`` only when bounds
    are ``FULL_RANGE``; on narrower bounds the flag is metadata only.
    """
    parsed = coerce_version(literal)
    if parsed is None:
        return admit_arbitrary and bounds == FULL_RANGE
    return matches_bounds_only(bounds, parsed)


def _decompose_dev0_gap(
    lower_trim: tuple[int, ...],
    upper_trim: tuple[int, ...],
    epoch: int,
) -> list[Version] | None:
    """Recursively decompose the gap ``[L.dev0, U.dev0)`` into wildcard prefixes.

    lower_trim and upper_trim are the trimmed release tuples (no trailing
    zeros) of L and U, with ``lower_trim < upper_trim`` lexicographically. The
    chain reaches U by sweeping at the diff level: emit ``==(C, c).*`` for c
    from ``lower_val`` up to ``upper_val - 1``, then recurse into the
    ``upper_val`` subtree when U has more depth. The gap is undecomposable
    when L has trailing components below the diff level: the chain can only
    increment, never escape L's subtree.
    """
    diff = 0
    while (
        diff < len(lower_trim)
        and diff < len(upper_trim)
        and lower_trim[diff] == upper_trim[diff]
    ):
        diff += 1

    # L has non-zero components past the diff level, so the chain is trapped
    # in L's subtree and cannot reach U.
    if len(lower_trim) > diff + 1:
        return None

    common = lower_trim[:diff]

    # When L_trim ends at the diff level, treat the missing position as zero:
    # L sits at the base of the (common)-subtree.
    lower_val = lower_trim[diff] if len(lower_trim) > diff else 0
    upper_val = upper_trim[diff]

    fragments = [
        Version.from_parts(epoch=epoch, release=(*common, segment))
        for segment in range(lower_val, upper_val)
    ]

    # The chain has reached (common + upper_val).dev0. If that is U, done.
    if len(upper_trim) == diff + 1:
        return fragments

    # Descend into the upper_val subtree. The recursive head has no trailing
    # components below its diff level, so decomposition always succeeds.
    tail = _decompose_dev0_gap((*common, upper_val), upper_trim, epoch)
    assert tail is not None
    return fragments + tail


def _detect_not_equal_wildcards(
    left_upper: UpperBound,
    right_lower: LowerBound,
) -> list[Version] | None:
    """Decompose a ``[L.dev0, U.dev0)`` gap into a chain of ``!=P.*`` prefixes.

    Returns the prefix list, or ``None`` when the gap shape is not
    wildcard-decomposable (mixed epochs, non-``.dev0`` endpoint, or L has
    trailing non-zero components below its diff level with U).
    """
    left_upper_v = left_upper.version
    right_lower_v = right_lower.version
    if isinstance(left_upper_v, BoundaryVersion) or isinstance(
        right_lower_v, BoundaryVersion
    ):
        return None

    if left_upper_v is None or right_lower_v is None:
        # First-interval upper or last-interval lower at infinity means the
        # interval is the universe and no second interval exists.
        return None  # pragma: no cover

    if left_upper.inclusive or not right_lower.inclusive:
        return None

    if not (_is_dev0_version(left_upper_v) and _is_dev0_version(right_lower_v)):
        return None

    if left_upper_v.epoch != right_lower_v.epoch:
        return None

    return _decompose_dev0_gap(
        trim_release(left_upper_v.release),
        trim_release(right_lower_v.release),
        left_upper_v.epoch,
    )


def _detect_equal_wildcards(
    lower: LowerBound,
    upper: UpperBound,
) -> list[Version] | None:
    """Decompose ``[V.dev0, W.dev0)`` into a chain of ``==P.*`` prefixes.

    Returns the prefix list (one entry per kept wildcard family), or ``None``
    when the interval's shape does not span a clean chain of ``==P.*``
    families (mixed epochs, non-``.dev0`` endpoint, or V has trailing
    non-zero components below its diff level with W). Reuses
    ``_decompose_dev0_gap``: an interval ``[V.dev0, W.dev0)`` is the
    set-theoretic gap a chain of ``!=P.*`` exclusions would carve out, with
    the chain reading instead as the kept families inside the interval.
    """
    if isinstance(lower.version, BoundaryVersion) or isinstance(
        upper.version, BoundaryVersion
    ):
        return None
    if lower.version is None or upper.version is None:
        return None
    if not lower.inclusive or upper.inclusive:
        return None
    if not (_is_dev0_version(lower.version) and _is_dev0_version(upper.version)):
        return None
    if lower.version.epoch != upper.version.epoch:
        return None

    return _decompose_dev0_gap(
        trim_release(lower.version.release),
        trim_release(upper.version.release),
        lower.version.epoch,
    )


def _wildcard_contains(prefix: Version, version: Version) -> bool:
    """Whether version matches ``=={prefix}.*``."""
    # Cross-epoch never arises under the canonical bounds invariant: gap
    # exclusions inherit the multi-wildcard outer's single epoch.
    if version.epoch != prefix.epoch:
        return False  # pragma: no cover
    prefix_length = len(prefix.release)
    return version.release[:prefix_length] == prefix.release


def _close_group(
    group_lower: LowerBound,
    group_upper: UpperBound,
    exclusions: list[str],
) -> list[list[str]] | None:
    """Encode one accumulated group, splitting multi-wildcard outers.

    A multi-wildcard ``[V.dev0, W.dev0)`` outer (W not V+1 in the last
    segment) becomes one ``==P.*`` group per kept family, each clean of
    the ``>=V.dev0,<W`` artifact that flips the recovered SpecifierSet's
    prereleases auto-detect. Accumulated ``!=V`` exclusions distribute
    to the family that contains them (``=={prefix}.*`` matches every
    version whose release shares ``prefix``'s release prefix); any other
    exclusion shape blocks the split. Anything outside the multi-family
    decomposition encodes as a single group via ``_encode_interval``.
    """
    wildcards = _detect_equal_wildcards(group_lower, group_upper)
    if wildcards is not None and len(wildcards) > 1:
        return _close_multi_wildcard(wildcards, exclusions)
    outer = _encode_interval(group_lower, group_upper)
    if outer is None:
        return None
    return [outer + exclusions]


def _close_multi_wildcard(
    wildcards: list[Version],
    exclusions: list[str],
) -> list[list[str]] | None:
    """Distribute ``!=V`` exclusions across the wildcards they fall into.

    Returns one group per wildcard, or ``None`` when an exclusion is not
    a plain ``!=V`` (the only shape that survives the gap-merging
    discipline once both sides are wildcard-decomposable) or its version
    falls outside every wildcard in the chain.
    """
    parsed: list[Version] = []
    for excl in exclusions:
        # ``!=V.*`` exclusions only accumulate when ``wildcard_split`` is
        # already False (i.e., one side is not wildcard-decomposable), and
        # the outer is therefore single-wildcard or non-wildcard, so this
        # branch is unreachable when the caller hit the multi-wildcard
        # path. ``InvalidVersion`` is likewise unreachable because every
        # exclusion comes from ``_detect_not_equal`` or
        # ``_detect_not_equal_wildcards``, both of which emit parseable
        # version strings. Defensive.
        if not excl.startswith("!=") or excl.endswith(".*"):
            return None  # pragma: no cover
        try:
            parsed.append(Version(excl[2:]))
        except InvalidVersion:  # pragma: no cover
            return None

    groups: list[list[str]] = []
    for prefix in wildcards:
        fragments = [f"=={prefix}.*"]
        for excl, version in zip(exclusions, parsed):
            if _wildcard_contains(prefix, version):
                fragments.append(excl)
        groups.append(fragments)

    # Every parsed exclusion must land inside some kept family.
    placed = {
        version
        for version in parsed
        if any(_wildcard_contains(prefix, version) for prefix in wildcards)
    }
    if len(placed) != len(set(parsed)):
        return None  # pragma: no cover

    return groups


def _strip_dev0_lower(fragment: str) -> str | None:
    """Strip ``>=V.dev0`` to ``>=V``, or return ``None`` if not the shape.

    Matches ``>=X[.Y]*[.postN].dev0`` (no pre, no local).
    """
    if not fragment.startswith(">="):
        return None
    try:
        version = Version(fragment[2:])
    except InvalidVersion:  # pragma: no cover
        return None
    if version.dev != 0 or version.pre is not None or version.local is not None:
        return None
    return f">={version.__replace__(dev=None)}"


def _strip_dev0_upper_pair(fragments: list[str]) -> list[str] | None:
    """Strip a ``<=V.postN.dev0,!=V.postN.dev0`` pair to its dev-less form.

    Returns ``None`` if no such pair is present. Unrelated ``!=`` exclusions
    in the same group are left in place.
    """
    upper_version: Version | None = None
    le_idx = -1
    for index, fragment in enumerate(fragments):
        if not fragment.startswith("<="):
            continue
        try:
            parsed = Version(fragment[2:])
        except InvalidVersion:  # pragma: no cover
            return None
        if (
            parsed.dev == 0
            and parsed.pre is None
            and parsed.post is not None
            and parsed.local is None
        ):
            le_idx = index
            upper_version = parsed
            break
    if upper_version is None:
        return None

    # ``_encode_upper`` always emits the ``<=V.postN.dev0`` /
    # ``!=V.postN.dev0`` pair together.
    ne_target = f"!={upper_version}"
    assert ne_target in fragments
    ne_idx = fragments.index(ne_target)

    stripped = upper_version.__replace__(dev=None)
    rewritten = list(fragments)
    rewritten[le_idx] = f"<={stripped}"
    rewritten[ne_idx] = f"!={stripped}"
    return rewritten


def _strip_synthetic_dev0(fragments: list[str]) -> list[str]:
    """Rewrite a group's fragment list to drop synthetic ``.dev0`` markers.

    Caller has already verified ``prereleases_configured is False``. Under
    that clamp the recovered SpecifierSet rejects every pre-release, so
    ``>=V`` and ``>=V.dev0`` (and the ``<=V,!=V`` pair vs its dev0 twin)
    accept the same versions. The cleaner spelling is what a maintainer
    would write for the same intent.
    """
    upper_pair = _strip_dev0_upper_pair(fragments)
    if upper_pair is not None:
        fragments = upper_pair
    return [_strip_dev0_lower(fragment) or fragment for fragment in fragments]


def _encode_grouped(bounds: list[Interval]) -> list[list[str]] | None:
    """Split bounds into disjoint groups, encoding each as fragments.

    Consecutive intervals whose gap is an ``!=V`` / ``!=V+local`` /
    ``!=V.*`` exclusion stay in one group, with that exclusion recorded
    as an ``!=`` fragment; any other gap starts a new group. Each group
    encodes as ``_encode_interval`` of its outer bounds plus its ``!=``
    fragments. Returns one fragment list per group, or ``None`` if any
    group's outer interval has no PEP 440 form.

    Adjacent ``==V.*`` wildcards joined by a ``!=X.*`` gap stay separate
    rather than merging through ``>=V.dev0,<W,!=X.*``: the synthetic
    ``.dev0`` would drift the recovered SpecifierSet's prereleases
    auto-detect, while each wildcard standalone encodes cleanly.
    """
    groups: list[list[str]] = []
    group_lower, group_upper = bounds[0]
    exclusions: list[str] = []
    for next_lower, next_upper in bounds[1:]:
        not_equal = _detect_not_equal(group_upper, next_lower)
        not_equal_wildcards = _detect_not_equal_wildcards(group_upper, next_lower)

        # Both sides decompose into ``==P.*`` chains, so merging through
        # the gap would force a ``>=V.dev0,<W,!=X.*`` outer with a
        # dev0-tainted lower; the standalone encodings (``==V.*`` or a
        # ``==V.*`` carrying any accumulated ``!=`` exclusions) stay clean.
        wildcard_split = (
            not_equal_wildcards is not None
            and _detect_equal_wildcards(group_lower, group_upper) is not None
            and _detect_equal_wildcards(next_lower, next_upper) is not None
        )
        if not_equal is not None:
            exclusions.append(f"!={not_equal}")
        elif not_equal_wildcards is not None and not wildcard_split:
            exclusions.extend(f"!={prefix}.*" for prefix in not_equal_wildcards)
        else:
            closed = _close_group(group_lower, group_upper, exclusions)
            if closed is None:
                return None
            groups.extend(closed)
            group_lower, exclusions = next_lower, []
        group_upper = next_upper

    closed = _close_group(group_lower, group_upper, exclusions)
    if closed is None:
        return None
    groups.extend(closed)
    return groups


class VersionRange:
    """A set of :class:`~packaging.version.Version` values accepted by a
    :class:`~packaging.specifiers.Specifier` or
    :class:`~packaging.specifiers.SpecifierSet`.

    Construct with :meth:`from_specifier` / :meth:`from_specifier_set`,
    or via :meth:`~packaging.specifiers.Specifier.to_range` /
    :meth:`~packaging.specifiers.SpecifierSet.to_range`. Compose with
    :meth:`intersection`, :meth:`union`, and :meth:`complement` (or the
    ``&`` / ``|`` / ``~`` operator aliases). Test membership with the
    ``in`` operator or :meth:`contains`, and convert back to a
    :class:`~packaging.specifiers.SpecifierSet` with
    :meth:`to_specifier_set` or :meth:`to_specifier_sets`.

    The configured pre-release policy of the originating specifier
    (``None``, ``True``, or ``False``) carries onto the range. It
    controls whether pre-releases are admitted under ``in``,
    :meth:`contains`, and :meth:`filter`. :meth:`intersection` and
    :meth:`union` require both operands to share the same policy;
    :meth:`complement` preserves the policy of its operand.

    >>> r = VersionRange.from_specifier_set(SpecifierSet(">=1.0,<2.0"))
    >>> "1.5" in r
    True
    >>> "2.0" in r
    False
    >>> bool(VersionRange.from_specifier_set(SpecifierSet(">=2.0,<1.0")))
    False

    PEP 440's ``===`` operator matches a candidate string verbatim
    (case-insensitive) rather than a set of
    :class:`~packaging.version.Version` values. Ranges built from
    ``===`` specifiers still support membership, set operations, and
    conversion back to a :class:`~packaging.specifiers.SpecifierSet`;
    matching follows the literal-equality rule instead of the
    version-ordering rule.

    Within the PEP 440 universe (no ``===`` literals and no arbitrary-
    string admission), De Morgan and double negation hold and ``r | ~r``
    admits every PEP 440 version. ``===`` ranges sit outside that
    universe and :meth:`complement` is one-way for them (``~~(===wat)``
    is the empty range, since the non-version literal drops out of the
    first complement). The arbitrary-admission flag on :meth:`full` /
    ``SpecifierSet("")`` is preserved by :meth:`complement` as metadata,
    so ``~~full() == full()`` even though ``~full()`` matches nothing.
    Use ``full(admit_arbitrary=False)`` to stay inside the PEP 440
    universe on both sides of the complement.
    """

    __slots__ = (
        "_admit",
        "_admit_arbitrary",
        "_bounds",
        "_prereleases",
        "_prereleases_configured",
        "_reject",
    )
    _bounds: tuple[Interval, ...]

    #: Whether this range matches non-version strings as well as versions.
    #: True only by construction, on the universal set from
    #: ``SpecifierSet("")`` (and :meth:`full`). Set algebra never invents
    #: arbitrary-string admission: intersection ANDs, union ORs, complement
    #: preserves. Decoupled from ``_bounds == FULL_RANGE`` so a canonicalized
    #: ``>=0.dev0`` (full bounds, but a real version specifier) does not
    #: admit arbitrary strings. Part of equality and hashing, since
    #: membership reads it.
    _admit_arbitrary: bool

    #: Case-folded strings the range admits in addition to its bounds.
    #: ``===wat`` produces ``_admit = {"wat"}``.
    _admit: frozenset[str]

    #: Case-folded strings the range rejects. Overrides ``_admit`` and
    #: ``_bounds``. Populated by :meth:`complement` of a range whose
    #: ``_admit`` was non-empty.
    _reject: frozenset[str]

    #: Resolved pre-release policy: ``True`` admits pre-releases, ``False``
    #: excludes them, ``None`` uses the PEP 440 default. Stamped from the
    #: originating specifier by the ``from_*`` factories. Carried through
    #: set algebra by :meth:`_propagate_prereleases`: under autodetect
    #: (``_prereleases_configured`` is ``None``), an autodetected ``True``
    #: on either operand wins; an explicit configured tag always wins.
    #: :meth:`complement` preserves the resolved tag. Read by :meth:`filter`
    #: only when its ``prereleases`` argument is ``None``; not part of
    #: equality, membership, or hashing.
    _prereleases: bool | None

    #: The raw configured pre-release override of the originating
    #: specifier (set): ``None`` when unset or unknown, ``True`` / ``False``
    #: when explicit. Unlike ``_prereleases`` (the resolved tag), this keeps
    #: autodetect-True and explicit-True distinct. :meth:`intersection` and
    #: :meth:`union` require this slot to match on both operands. Part of
    #: equality and hashing, since membership reads it.
    _prereleases_configured: bool | None

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
        admit_arbitrary: bool = False,
    ) -> VersionRange:
        """Internal factory; bypasses :meth:`__new__`.

        Drops admit literals the structural part already admits, and reject
        literals it does not match anyway. Reject wins over admit on overlap.
        """
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
        instance._prereleases = None
        instance._prereleases_configured = None
        return instance

    def _has_literals(self) -> bool:
        """``True`` when ``_admit`` or ``_reject`` is non-empty."""
        return bool(self._admit) or bool(self._reject)

    def _arbitrary_active(self) -> bool:
        """``True`` when ``_admit_arbitrary`` actually admits anything.

        The flag propagates through set algebra (AND on intersection, OR
        on union, preserved by complement) but fires admission only when
        bounds are ``FULL_RANGE``; on narrower bounds it is metadata that
        rides along until a later widening reactivates it.
        """
        return self._admit_arbitrary and self._bounds == FULL_RANGE

    def _check_policy_compat(self, other: VersionRange) -> None:
        """Refuse combining ranges with different pre-release policies.

        Also validates the operand type so the public set-algebra methods
        raise :exc:`TypeError` on a wrong-type argument instead of leaking
        an :exc:`AttributeError` from the private slot access below.
        """
        if not isinstance(other, VersionRange):
            raise TypeError(f"expected VersionRange, got {type(other).__name__}")

        if self._prereleases_configured != other._prereleases_configured:
            raise ValueError(
                "Cannot combine VersionRange operands with different "
                f"pre-release policies: {self._prereleases_configured!r} "
                f"and {other._prereleases_configured!r}"
            )

    def _propagate_prereleases(self, other: VersionRange, result: VersionRange) -> None:
        """Carry the shared pre-release policy onto a freshly built ``result``.

        ``self`` and ``other`` must already have been confirmed compatible
        via :meth:`_check_policy_compat`. When the configured tag is
        ``None`` (autodetect), an autodetected ``True`` on either operand
        wins so a pre-release seen on one side carries through the
        combination; otherwise the autodetected tag resolves to ``None``
        because :func:`resolve_prereleases` never returns ``False`` when
        no explicit policy is configured.
        """
        result._prereleases_configured = self._prereleases_configured
        if self._prereleases_configured is not None:
            result._prereleases = self._prereleases_configured
        elif self._prereleases is True or other._prereleases is True:
            result._prereleases = True
        else:
            result._prereleases = None

    def _restamp(self, *, resolved: bool | None, configured: bool | None) -> None:
        """Set the pre-release policy slots on a range built by an external
        factory.

        Friend API for :class:`packaging.specifiers.Specifier` /
        :class:`packaging.specifiers.SpecifierSet` so the ``ranges`` <->
        ``specifiers`` coupling lives in one place. Set algebra carries
        policy through :meth:`_propagate_prereleases`; this is the
        cache-refresh path.
        """
        self._prereleases = resolved
        self._prereleases_configured = configured

    @classmethod
    def empty(
        cls,
        *,
        admit_arbitrary: bool = False,
        prereleases: bool | None = None,
    ) -> VersionRange:
        """Return the empty range. No version satisfies it.

        ``prereleases`` stamps the configured policy so the result can
        combine with ranges built from a
        :class:`~packaging.specifiers.SpecifierSet` carrying the same
        policy.

        ``admit_arbitrary=True`` carries the arbitrary-string flag as
        metadata. The range still admits nothing under ``in`` /
        :meth:`contains` / :meth:`filter`; the flag rides along through
        complement and union so a later widening to ``FULL_RANGE`` bounds
        reactivates it. Intersection with a False operand strips it.
        Default is ``False`` so that ``r | empty()`` preserves
        ``r._admit_arbitrary`` structurally.

        >>> VersionRange.empty().is_empty
        True
        >>> "1.0" in VersionRange.empty()
        False
        >>> e = VersionRange.empty(admit_arbitrary=True)
        >>> e.is_empty
        True
        >>> "garbage" in e
        False
        >>> e == ~VersionRange.full()
        True
        >>> "garbage" in (e | VersionRange.full())
        True
        """
        result = cls._build((), admit_arbitrary=admit_arbitrary)
        if prereleases is not None:
            result._restamp(resolved=prereleases, configured=prereleases)
        return result

    @classmethod
    def full(
        cls,
        *,
        admit_arbitrary: bool = True,
        prereleases: bool | None = None,
    ) -> VersionRange:
        """Return the full range. Every PEP 440 version satisfies it.

        ``prereleases`` stamps the configured policy so the result can
        combine with ranges built from a
        :class:`~packaging.specifiers.SpecifierSet` carrying the same
        policy.

        ``admit_arbitrary=False`` restricts the range to PEP 440 versions
        only (the same shape as ``SpecifierSet(">=0.dev0").to_range()``);
        its complement is :meth:`empty`. ``admit_arbitrary`` propagates
        through set algebra: intersection ANDs, union ORs, complement
        preserves. Default is ``True`` so that ``r & full()`` preserves
        ``r._admit_arbitrary`` structurally.

        >>> "1.0" in VersionRange.full()
        True
        >>> "garbage" in VersionRange.full()
        True
        >>> "garbage" in VersionRange.full(admit_arbitrary=False)
        False
        >>> ~VersionRange.full(admit_arbitrary=False) == VersionRange.empty()
        True
        """
        result = cls._build(FULL_RANGE, admit_arbitrary=admit_arbitrary)
        if prereleases is not None:
            result._restamp(resolved=prereleases, configured=prereleases)
        return result

    @classmethod
    def singleton(
        cls, version: Version | str, *, prereleases: bool | None = None
    ) -> VersionRange:
        """Return the strict singleton range ``{version}``.

        Built as the closed interval ``[version, version]`` with strict
        equality, intended for users implementing algorithms that need a
        singleton from set theory.

        Pass ``prereleases=True``/``False`` to stamp the configured
        policy so the result can combine with ranges built from a
        :class:`~packaging.specifiers.SpecifierSet` carrying the same
        policy.

        >>> r = VersionRange.singleton("1.2.3")
        >>> "1.2.3" in r
        True
        >>> "1.2.4" in r
        False

        ``Specifier("==V")`` matches ``V+local`` too (PEP 440), so the
        strict singleton is narrower:

        >>> "1.0+local" in VersionRange.singleton("1.0")
        False
        >>> "1.0+local" in Specifier("==1.0")
        True

        For the wider ``==V`` semantics use :meth:`from_specifier` with
        ``Specifier("==V")`` or :meth:`from_specifier_set` with
        ``SpecifierSet("==V")``:

        >>> r = VersionRange.from_specifier(Specifier("==1.0"))
        >>> "1.0+local" in r
        True

        :raises packaging.version.InvalidVersion: if version is a
            string that does not parse as a PEP 440 version.
        """
        if not isinstance(version, Version):
            version = Version(version)
        lower = LowerBound(version, inclusive=True)
        upper = UpperBound(version, inclusive=True)
        result = cls._build(((lower, upper),))
        if prereleases is not None:
            result._restamp(resolved=prereleases, configured=prereleases)
        return result

    def intersection(self, other: VersionRange) -> VersionRange:
        """Range containing exactly the versions in both self and other.

        Both operands must share the same configured pre-release policy
        (``None``, ``True``, or ``False``); otherwise :exc:`ValueError` is
        raised. The shared policy is carried onto the result.

        >>> a = VersionRange.from_specifier_set(SpecifierSet(">=1.0"))
        >>> b = VersionRange.from_specifier_set(SpecifierSet("<2.0"))
        >>> ab = VersionRange.from_specifier_set(SpecifierSet(">=1.0,<2.0"))
        >>> a.intersection(b) == ab
        True
        """
        self._check_policy_compat(other)

        new_bounds = tuple(intersect_ranges(self._bounds, other._bounds))

        # Arbitrary-string admission survives only when both sides admit.
        combined_arb = self._admit_arbitrary and other._admit_arbitrary
        if not self._has_literals() and not other._has_literals():
            result = self._build(new_bounds, admit_arbitrary=combined_arb)
        else:
            result = self._combine_literals(
                other, new_bounds, intersect=True, admit_arbitrary=combined_arb
            )

        self._propagate_prereleases(other, result)
        return result

    def union(self, other: VersionRange) -> VersionRange:
        """Range containing every version in self or other.

        Both operands must share the same configured pre-release policy
        (``None``, ``True``, or ``False``); otherwise :exc:`ValueError` is
        raised. The shared policy is carried onto the result.

        >>> a = VersionRange.singleton("1.0")
        >>> b = VersionRange.singleton("2.0")
        >>> "1.0" in a.union(b) and "2.0" in a.union(b)
        True
        >>> "1.5" in a.union(b)
        False
        """
        self._check_policy_compat(other)

        new_bounds = tuple(_union_ranges(self._bounds, other._bounds))

        # Either universal side makes the union admit arbitrary strings.
        combined_arb = self._admit_arbitrary or other._admit_arbitrary
        if not self._has_literals() and not other._has_literals():
            result = self._build(new_bounds, admit_arbitrary=combined_arb)
        else:
            result = self._combine_literals(
                other, new_bounds, intersect=False, admit_arbitrary=combined_arb
            )

        # ``r | full()`` collapses to the canonical universal range when
        # both sides carry the autodetect default. An explicit policy
        # (``SpecifierSet("", prereleases=True).to_range() | r``) must
        # survive the union, so only the autodetect-only case collapses;
        # ``_check_policy_compat`` already required the configured tags
        # to match, so checking ``self`` covers both operands.
        if (
            result._bounds == FULL_RANGE
            and result._admit_arbitrary
            and not result._has_literals()
            and self._prereleases_configured is None
        ):
            result._prereleases_configured = None
            result._prereleases = None
            return result

        self._propagate_prereleases(other, result)
        return result

    def complement(self) -> VersionRange:
        """Range containing every version not in self.

        Preserves the configured pre-release policy of self. The
        arbitrary-string flag is preserved as metadata, so
        ``~~full() == full()`` holds even though ``~full()`` matches
        nothing under membership (it equals
        ``empty(admit_arbitrary=True)``).

        >>> r = VersionRange.from_specifier(Specifier(">=1.0"))
        >>> "0.5" in r.complement()
        True
        >>> "1.5" in r.complement()
        False
        >>> r.complement().complement() == r
        True
        """
        if not self._has_literals():
            result = self._build(
                tuple(_complement_ranges(self._bounds)),
                admit_arbitrary=self._admit_arbitrary,
            )
        else:
            # Swap the admit and reject sets, complement the bounds.
            # ``_build`` drops anything now redundant against the new bounds.
            result = self._build(
                tuple(_complement_ranges(self._bounds)),
                admit=self._reject,
                reject=self._admit,
                admit_arbitrary=self._admit_arbitrary,
            )
        result._prereleases = self._prereleases
        result._prereleases_configured = self._prereleases_configured
        return result

    def _combine_literals(
        self,
        other: VersionRange,
        new_bounds: tuple[Interval, ...],
        *,
        intersect: bool,
        admit_arbitrary: bool,
    ) -> VersionRange:
        """Resolve admit/reject for ``self & other`` or ``self | other``.

        For each literal seen on either side, decide whether the combined
        predicate (AND for intersection, OR for union) admits or excludes
        it. ``_build`` drops admits the structural part already covers and
        rejects the structural part already excludes.
        """
        admits: set[str] = set()
        rejects: set[str] = set()
        for literal in self._admit | self._reject | other._admit | other._reject:
            self_in = self._matches_literal(literal)
            other_in = other._matches_literal(literal)
            want = (self_in and other_in) if intersect else (self_in or other_in)
            if want:
                # ``_build`` drops admits the new bounds already cover, so
                # no need to pre-filter via ``_struct_admits`` here.
                admits.add(literal)
            else:
                rejects.add(literal)
        return self._build(
            new_bounds,
            admit=frozenset(admits),
            reject=frozenset(rejects),
            admit_arbitrary=admit_arbitrary,
        )

    def _matches_literal(self, literal: str) -> bool:
        """Whether literal (case-folded) matches this range's predicate.

        Mirrors :meth:`__contains__`: reject then admit win, then a
        parseable version is tested against the bounds. A non-version
        string matches only via admit or live arbitrary admission.
        """
        if literal in self._reject:
            return False
        if literal in self._admit:
            return True
        parsed = coerce_version(literal)
        if parsed is None:
            return self._arbitrary_active()
        return self._matches_bounds(parsed)

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

        With prereleases ``None`` the PEP 440 default applies:
        pre-releases are buffered and only emitted if no final release
        in iterable is in range.

        The signature mirrors
        :meth:`~packaging.specifiers.SpecifierSet.filter` exactly, including
        the admission of unparsable strings for the empty ``SpecifierSet("")``
        and the case-insensitive literal match for ``===``.

        >>> r = VersionRange.from_specifier_set(SpecifierSet(">=1.0,<2.0"))
        >>> list(r.filter(["0.9", "1.5", "2.0"]))
        ['1.5']
        """
        if prereleases is None:
            prereleases = self._prereleases
        # A bounds-only range (no admit/reject literals, no live
        # arbitrary admission) skips the admission dispatch entirely.
        arbitrary_active = self._arbitrary_active()
        if not self._admit and not self._reject and not arbitrary_active:
            return filter_by_ranges(self._bounds, iterable, key, prereleases)
        # Universal range: every item is admitted, so parse only enough to
        # decide pre-release buffering. Matches ``SpecifierSet("").filter``.
        if arbitrary_active and not self._admit and not self._reject:
            return _filter_universal(iterable, key, prereleases)
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
        arbitrary_active = self._arbitrary_active()

        def admit(item: Any) -> tuple[bool, Version | None]:  # noqa: ANN401
            raw: Version | str = item if key is None else key(item)
            raw_lower = str(raw).lower()
            if reject_set and raw_lower in reject_set:
                return False, None
            if admit_set and raw_lower in admit_set:
                return True, coerce_version(raw)
            parsed = coerce_version(raw)
            if parsed is None:
                # Non-parseable strings match only when arbitrary
                # admission is live.
                return arbitrary_active, None
            if not self._matches_bounds(parsed):
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
        """Return the :class:`VersionRange` accepted by specifier.

        >>> isinstance(VersionRange.from_specifier(Specifier(">=1.0")), VersionRange)
        True

        ``===L`` literals are case-folded at construction
        (``Specifier("===WAT")`` and ``Specifier("===wat")`` produce
        equal ranges), even though
        :class:`~packaging.specifiers.Specifier` and
        :class:`~packaging.specifiers.SpecifierSet` treat the literal
        case-sensitively under their own ``==``. Both layers match
        candidates case-insensitively at runtime (the PEP 440 rule), so
        this only affects structural equality. A dict keyed by
        :class:`VersionRange` will treat ``===WAT`` and ``===wat`` as
        the same key; a dict keyed by
        :class:`~packaging.specifiers.SpecifierSet` keeps them distinct.
        """
        operator = specifier.operator
        version = specifier.version
        if operator == "===":
            result = cls._build(bounds=(), admit=frozenset({version.lower()}))
        else:
            result = cls._build(bounds=bounds_for_spec(operator, version))
        result._prereleases, result._prereleases_configured = (
            specifier._range_prereleases()
        )
        return result

    @classmethod
    def from_specifier_set(cls, specifier_set: SpecifierSet) -> VersionRange:
        """Return the :class:`VersionRange` accepted by specifier_set.

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
        # Fast path: a rangelike-only set folds per-specifier bounds via the
        # shared helper, going through each Specifier's cached ``_to_ranges``
        # so a later ``filter`` / ``contains`` reuses the parse.  ``===``
        # introduces literal-string admission that bare bounds cannot carry,
        # so those fall back to the per-specifier fold which routes literals
        # through ``_combine_literals``.
        if not specifier_set:
            result = cls.full()
        elif not specifier_set._has_arbitrary:
            result = cls._build(
                bounds=intersect_specifier_bounds(
                    spec._to_ranges() for spec in specifier_set
                )
            )
        else:
            result = cls.full()
            for spec in specifier_set:
                # ``intersection`` rejects any mismatched configured policy.
                # Inside the set the per-spec configured tag is an
                # implementation detail (the set-level tag is what survives
                # below), so neutralize it here to keep the fold from
                # raising on construction.
                operand = cls.from_specifier(spec)
                operand._prereleases_configured = None
                result = result.intersection(operand)

        result._prereleases, result._prereleases_configured = (
            specifier_set._range_prereleases()
        )
        return result

    def to_specifier_set(self) -> SpecifierSet | None:
        """Return a single
        :class:`~packaging.specifiers.SpecifierSet` that matches the
        same versions as self under ``in`` and
        :meth:`~packaging.specifiers.SpecifierSet.filter`, or ``None`` if
        no such set exists.

        :class:`~packaging.specifiers.SpecifierSet` cannot express every
        range. PEP 440's operator set has no syntax for the strict
        singleton ``{V}`` or for the bounds produced by complementing
        ``>V``; for those ranges the result is ``None``. Disjoint unions
        of two or more ``==V.*`` families (e.g. ``==1.* | ==3.*``) also
        return ``None``, since the only single-set spelling would shift
        the recovered set's pre-release behaviour. Use
        :meth:`to_specifier_sets` when a tuple of specifier sets is
        acceptable. The empty range maps to ``SpecifierSet("<0")``
        (``<0`` excludes ``0.dev0``, the smallest PEP 440 version); the
        full range maps to the empty ``SpecifierSet("")``.

        Version membership round-trips through this method. An all-
        versions range that did not come from ``SpecifierSet("")`` (for
        example ``Specifier(">=0.dev0")`` after min-version
        canonicalization) maps to ``SpecifierSet(">=0.dev0")`` rather
        than the empty set, so the ``SpecifierSet("")`` quirk of also
        matching non-version strings is not introduced.

        Under ``prereleases=None`` (autodetect) or ``prereleases=True``,
        feeding the result back through :meth:`from_specifier_set`
        returns a range structurally equal to self. Under explicit
        ``prereleases=False``, two ranges that match the same versions
        can have different bound shapes (for example ``>=1.5.dev0`` and
        ``>=1.5`` both reject every pre-release under that policy); the
        recovered range matches the same versions as self but may not
        be structurally equal to it.

        Filter equivalence is at the configured policy: an explicit
        ``prereleases=True`` override on the returned set can admit
        versions self would reject. For example
        ``SpecifierSet(">=1.0.dev0", prereleases=False).to_range()`` is
        encoded as ``>=1.0`` (the ``.dev0`` marker is stripped because
        ``False`` clamps pre-releases at filter time), so the recovered
        set's ``filter(items, prereleases=True)`` admits ``1.0`` only,
        while the source range under the same override admits ``1.0.dev0``,
        ``1.0a1``, and ``1.0``.

        >>> r = VersionRange.from_specifier_set(SpecifierSet(">=1.0,<2.0"))
        >>> str(r.to_specifier_set())
        '<2.0,>=1.0'
        >>> VersionRange.singleton("1.5").to_specifier_set() is None
        True
        """
        sets = self.to_specifier_sets()
        if sets is None or len(sets) != 1:
            return None
        result = sets[0]

        # SpecifierSet has no way to say ">=V.dev0 but do NOT imply
        # pre-releases": a synthetic ``.dev0`` literal flips the
        # recovered set's prereleases auto-detect, and a stripped form
        # would lose it. Under cfg=None the source has no explicit
        # clamp, so any mismatch between source and recovered
        # auto-detect is silent filter drift; report as ``None``. The
        # empty range filters nothing regardless of its tag, so the
        # check is skipped there.
        # ``_drift_guarded_pieces`` runs this same check on the
        # pieces; a drifted single piece returns ``None`` above. Assert
        # to surface any regression in the helper.
        assert not (
            self._prereleases_configured is None
            and not self.is_empty
            and result.prereleases != self._prereleases
        )
        return result

    def to_specifier_sets(self) -> tuple[SpecifierSet, ...] | None:
        """Return a tuple of
        :class:`~packaging.specifiers.SpecifierSet` whose union, fed
        back through :meth:`from_specifier_set`, reproduces self, or
        ``None`` if no such tuple exists.

        Looser than :meth:`to_specifier_set`: each maximal run of
        intervals joined by ``!=V`` / ``!=V.*`` gaps becomes one
        :class:`~packaging.specifiers.SpecifierSet`, and genuinely
        disjoint runs become separate ones. Admit literals (from
        ``===L``) become their own ``===L`` pieces alongside the bound
        groups. ``None`` when some piece has no PEP 440 form (a reject
        literal, the strict singleton produced by :meth:`singleton`, or
        arbitrary-string admission combined with narrowed bounds), or
        when the recovered pieces would silently change the source's
        pre-release autodetect on round-trip (see below).

        Under ``prereleases=None`` (autodetect) or ``prereleases=True``,
        feeding the returned sets back through :meth:`from_specifier_set`
        and unioning the results yields a range structurally equal to
        self. Under explicit ``prereleases=False``, two ranges that match
        the same versions can have different bound shapes (for example
        ``>=1.5.dev0`` and ``>=1.5`` both reject every pre-release under
        that policy); the recovered range matches the same versions as
        self but may not be structurally equal to it.

        Use :meth:`to_specifier_set` when a single filter-equivalent
        set is required.

        >>> r = (
        ...     VersionRange.from_specifier_set(SpecifierSet(">=1.0,<2.0"))
        ...     | VersionRange.from_specifier_set(SpecifierSet(">=3.0,<4.0"))
        ... )
        >>> [str(s) for s in r.to_specifier_sets()]
        ['<2.0,>=1.0', '<4.0,>=3.0']
        >>> VersionRange.singleton("1.5").to_specifier_sets() is None
        True

        Drift example: the bounds of ``>=1.0a1 & >=2.0`` canonicalize to
        ``[2.0, +inf)``, which the encoder would spell ``>=2.0``.
        ``SpecifierSet(">=2.0")`` autodetects ``prereleases=None``, but
        the source autodetected :data:`True` from ``>=1.0a1``. Round-tripping
        through ``>=2.0`` would reject ``2.5a1`` while the source admits
        it, so ``None`` is returned instead.
        """
        from .specifiers import SpecifierSet  # noqa: PLC0415

        if self._reject:
            return None
        # ``_admit_arbitrary=True`` only encodes at ``FULL_RANGE`` bounds
        # (as ``SpecifierSet("")``); on narrower bounds the flag has no
        # PEP 440 form. Checked before :meth:`is_empty` so an empty
        # range carrying the flag is not silently encoded as ``<0`` and
        # stripped of the flag on round-trip.
        if self._admit_arbitrary and self._bounds != FULL_RANGE:
            return None
        if self.is_empty:
            return (SpecifierSet("<0", prereleases=self._prereleases_configured),)

        admit_pieces = tuple(
            SpecifierSet(f"==={literal}", prereleases=self._prereleases_configured)
            for literal in sorted(self._admit)
        )

        if not self._bounds:
            return self._drift_guarded_pieces(admit_pieces) if admit_pieces else None
        if self._bounds == FULL_RANGE:
            if self._admit_arbitrary:
                full_spec = ""
            elif self._prereleases_configured is False:
                # Explicit False clamps pre-releases at filter time, so
                # ``>=0`` and ``>=0.dev0`` admit the same versions; emit
                # the cleaner spelling. ``SpecifierSet("")`` would also
                # admit arbitrary strings, which this branch does not.
                full_spec = ">=0"
            else:
                full_spec = ">=0.dev0"
            full_piece = SpecifierSet(
                full_spec, prereleases=self._prereleases_configured
            )
            return self._drift_guarded_pieces((*admit_pieces, full_piece))

        # One SpecifierSet per disjoint group; ``!=`` gaps stay merged
        # inside their group.
        groups = _encode_grouped(list(self._bounds))
        if groups is None:
            return None

        # Under explicit ``prereleases=False`` the recovered set clamps
        # pre-releases at filter time regardless of the bound shape, so
        # the synthetic ``.dev0`` markers some shapes carry are filter-
        # equivalent to the dev-stripped spelling. Rewrite to the
        # cleaner form.
        if self._prereleases_configured is False:
            groups = [_strip_synthetic_dev0(group) for group in groups]
        bound_pieces = tuple(
            SpecifierSet(",".join(group), prereleases=self._prereleases_configured)
            for group in groups
        )
        return self._drift_guarded_pieces(admit_pieces + bound_pieces)

    def _drift_guarded_pieces(
        self, pieces: tuple[SpecifierSet, ...]
    ) -> tuple[SpecifierSet, ...] | None:
        """Return ``pieces`` if their union round-trips without filter drift.

        Mirrors the single-set drift guard in :meth:`to_specifier_set`.
        Under ``_prereleases_configured=None`` the source has no explicit
        clamp, so any mismatch between source and recovered auto-detect
        is silent filter drift; report as ``None``. The empty range
        filters nothing regardless of its tag, so the check is skipped
        there.
        """
        if self._prereleases_configured is not None:
            return pieces
        # ``to_specifier_sets`` returns ``(SpecifierSet("<0"),)`` for an
        # empty range before reaching this helper.
        assert not self.is_empty
        recovered = True if any(piece.prereleases for piece in pieces) else None
        if recovered != self._prereleases:
            return None
        return pieces

    def __reduce__(self) -> tuple[object, ...]:
        # Pickle and ``copy`` reconstruct via :func:`_new_version_range`,
        # which bypasses the :meth:`__new__` guard while preserving
        # ``type(self)`` so subclasses survive the round-trip. State is the
        # primitive 6-tuple from :meth:`__getstate__`; pickle then calls
        # :meth:`__setstate__` on the new instance.
        return (_new_version_range, (type(self),), self.__getstate__())

    def __getstate__(self) -> _VersionRangeState:
        # Primitive 6-tuple (see ``_VersionRangeState``) so the format
        # stays stable across packaging releases. Covers every slot read
        # by :meth:`__eq__`, :meth:`__hash__`, :meth:`__repr__`, and
        # :meth:`contains`.
        return (
            tuple(
                (_pack_bound(lower), _pack_bound(upper))
                for lower, upper in self._bounds
            ),
            tuple(sorted(self._admit)),
            tuple(sorted(self._reject)),
            self._admit_arbitrary,
            self._prereleases,
            self._prereleases_configured,
        )

    def __setstate__(self, state: object) -> None:
        # Stable 6-tuple ``_VersionRangeState`` format. Validates shape so a
        # future-format pickle (extra slots) or a bytes blob from an
        # unrelated source raises a clear :exc:`TypeError`. An unknown
        # :data:`BoundaryKind` code surfaces as :exc:`ValueError` from
        # :func:`_unpack_inner` instead of a bare :exc:`KeyError`.
        if isinstance(state, tuple) and len(state) == 6:
            packed_bounds, admit, reject, admit_arbitrary, pre, pre_cfg = state
            if (
                isinstance(packed_bounds, tuple)
                and isinstance(admit, tuple)
                and isinstance(reject, tuple)
                and isinstance(admit_arbitrary, bool)
                and (pre is None or isinstance(pre, bool))
                and (pre_cfg is None or isinstance(pre_cfg, bool))
            ):
                try:
                    bounds = tuple(
                        (
                            LowerBound(*_unpack_inner(lower)),
                            UpperBound(*_unpack_inner(upper)),
                        )
                        for lower, upper in packed_bounds
                    )
                except (KeyError, TypeError, ValueError, InvalidVersion) as exc:
                    raise TypeError(
                        f"Cannot restore VersionRange from {state!r}"
                    ) from exc
                self._bounds = bounds
                self._admit = frozenset(admit)
                self._reject = frozenset(reject)
                self._admit_arbitrary = admit_arbitrary
                self._prereleases = pre
                self._prereleases_configured = pre_cfg
                return

        raise TypeError(f"Cannot restore VersionRange from {state!r}")

    @property
    def is_empty(self) -> bool:
        """``True`` if no version or string satisfies this range.

        ``_admit_arbitrary`` on empty bounds is metadata only (it admits
        nothing), so ``empty(admit_arbitrary=True)`` reads as empty here.

        >>> VersionRange.from_specifier_set(SpecifierSet(">=2,<1")).is_empty
        True
        >>> VersionRange.from_specifier_set(SpecifierSet(">=1,<2")).is_empty
        False
        >>> VersionRange.empty(admit_arbitrary=True).is_empty
        True
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
        if self._arbitrary_active():
            # Live arbitrary matches are non-version strings, not pre-releases.
            return False
        for literal in self._admit:
            parsed = coerce_version(literal)
            if parsed is None or not parsed.is_prerelease:
                return False
        if self._bounds:
            return ranges_are_prerelease_only(self._bounds)
        return True

    def __bool__(self) -> bool:
        """``False`` when the range is empty, ``True`` otherwise.

        >>> bool(VersionRange.from_specifier_set(SpecifierSet(">=1,<2")))
        True
        >>> bool(VersionRange.from_specifier_set(SpecifierSet(">=2,<1")))
        False
        """
        return bool(self._bounds) or bool(self._admit)

    def contains(
        self,
        item: Version | str,
        prereleases: bool | None = None,
        installed: bool | None = None,
    ) -> bool:
        """Return whether item is contained in this range.

        :param item:
            The item to check for, which can be a version string or a
            :class:`~packaging.version.Version` instance.
        :param prereleases:
            Whether or not to match prereleases against this range. If set
            to ``None`` (the default), the range's own pre-release policy
            is used; ranges built from specifiers that did not explicitly
            request a policy follow the recommendation from :pep:`440` and
            match prereleases when there are no other versions.
        :param installed:
            Whether or not the item is installed. If set to ``True``, it
            will accept prerelease versions even if the range does not
            otherwise allow them.

        Unparsable strings do not match, except where the full
        ``SpecifierSet`` would also match: the full range admits any
        string, and a ``===`` range admits items whose string equals the
        literal case-insensitively.

        >>> r = VersionRange.from_specifier_set(SpecifierSet(">=1.0,<2.0"))
        >>> r.contains("1.5")
        True
        >>> r.contains("2.0")
        False
        >>> r2 = SpecifierSet(">=1.0", prereleases=False).to_range()
        >>> r2.contains("1.5a1")
        False
        >>> r2.contains("1.5a1", prereleases=True)
        True
        >>> r2.contains("1.5a1", installed=True)
        True
        >>> r2.contains("1.5", installed=True)
        True

        :raises TypeError: if ``item`` is not a :class:`str` or
            :class:`~packaging.version.Version`.

        .. versionadded:: 26.3
        """
        if not isinstance(item, (str, Version)):
            raise TypeError(
                f"VersionRange.contains() expected str or Version, "
                f"got {type(item).__name__}"
            )
        # Mirror SpecifierSet.contains: when ``installed`` is truthy and the
        # item parses to a pre-release Version, force ``prereleases=True``
        # regardless of any explicit ``prereleases=False`` or the range's
        # own configured policy.
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
                # Mirror SpecifierSet.contains: an explicit
                # ``prereleases=False`` excludes a literal that parses to a
                # pre-release version. Autodetect-False (configured=None) does
                # not, matching PEP 440's "match prereleases when there are
                # no other versions" default.
                if effective_pre is False:
                    literal_parsed = coerce_version(item_str)
                    if literal_parsed is not None and literal_parsed.is_prerelease:
                        return False
                return True
        if not isinstance(item, Version):
            if parsed is None:
                parsed = coerce_version(item)
            if parsed is None:
                # Mirror SpecifierSet.contains: anything that doesn't parse
                # to a Version falls through to arbitrary admission, which
                # fires only when the flag is live (bounds at ``FULL_RANGE``).
                return self._arbitrary_active()
            item = parsed
        if effective_pre is False and item.is_prerelease:
            return False
        return self._matches_bounds(item)

    def __contains__(self, item: Version | str) -> bool:
        """Return whether item is contained in this range.

        Forwards to :meth:`contains` with default arguments, so the ``in``
        operator follows the range's own pre-release policy and does not
        apply the ``installed`` override.

        >>> r = VersionRange.from_specifier_set(SpecifierSet(">=1.0,<2.0"))
        >>> "1.5" in r
        True
        >>> "2.0" in r
        False
        """
        return self.contains(item)

    def _matches_bounds(self, item: Version) -> bool:
        """Bound-only membership check; ignores admit/reject."""
        return matches_bounds_only(self._bounds, item)

    def __eq__(self, other: object) -> bool:
        """Structural equality.

        Two ranges compare equal when every input to :meth:`contains`
        and :meth:`__contains__` agrees: the bounds, the ``===`` admit
        literals, any reject literals, the arbitrary-string admission
        flag, and the configured pre-release policy. Ranges that agree
        on these accept the same items under ``in``. The converse does
        not always hold: two ranges that admit the same set of versions
        may still differ structurally, since ``===L`` admit literals are
        case-folded and some bound shapes that admit the same versions
        differ in spelling.

        Case-folding under ``===L`` means ``===WAT`` and ``===wat``
        produce equal ranges here, while
        :class:`~packaging.specifiers.SpecifierSet` keeps them distinct
        under its own ``==``. Users who need case-distinct keys should
        key by :class:`~packaging.specifiers.SpecifierSet`, not by
        :class:`VersionRange`.

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
            and self._admit_arbitrary == other._admit_arbitrary
            and self._prereleases_configured == other._prereleases_configured
        )

    def __hash__(self) -> int:
        return hash(
            (
                self._bounds,
                self._admit,
                self._reject,
                self._admit_arbitrary,
                self._prereleases_configured,
            )
        )

    def __repr__(self) -> str:
        """Human-readable representation for debugging.

        Shows the interval form, the ``===`` admit literals, the
        ``arbitrary`` marker when the range admits non-version strings,
        and the ``pre=`` marker when the range has an explicit
        pre-release policy. Some bounds carry a ``[KIND]`` suffix to
        disambiguate ranges that differ structurally but share a printed
        version (for example, ``==1.0`` and the strict singleton
        ``singleton("1.0")``).

        >>> VersionRange.from_specifier_set(SpecifierSet(">=1.0,<2.0"))
        <VersionRange '[1.0, 2.0.dev0)'>
        >>> VersionRange.from_specifier_set(SpecifierSet(""))
        <VersionRange '(-inf, +inf)' arbitrary>
        >>> VersionRange.from_specifier_set(SpecifierSet(">=2.0,<1.0"))
        <VersionRange '(empty)'>
        >>> VersionRange.from_specifier(Specifier("===wat"))
        <VersionRange '{wat}'>
        >>> VersionRange.from_specifier_set(SpecifierSet(">=1.0", prereleases=False))
        <VersionRange '[1.0, +inf)' pre=False>
        >>> VersionRange.from_specifier(Specifier("==1.0"))
        <VersionRange '[1.0, 1.0[AFTER_LOCALS]]'>
        >>> VersionRange.from_specifier(Specifier(">1.0"))
        <VersionRange '(1.0[AFTER_POSTS], +inf)'>
        """
        parts: list[str] = []
        if self._bounds:
            parts.append(
                " | ".join(
                    f"{_format_lower(lower)}, {_format_upper(upper)}"
                    for lower, upper in self._bounds
                )
            )
        if self._admit:
            parts.append("{" + ", ".join(sorted(self._admit)) + "}")

        body = " | ".join(parts) if parts else "(empty)"
        if self._reject:
            body = f"{body} \\ {{{', '.join(sorted(self._reject))}}}"

        tail = ""
        if self._admit_arbitrary:
            tail += " arbitrary"
        if self._prereleases_configured is not None:
            tail += f" pre={self._prereleases_configured}"
        return f"<{self.__class__.__name__} {body!r}{tail}>"
