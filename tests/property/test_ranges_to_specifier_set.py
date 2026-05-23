# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.

"""Property tests for ``VersionRange.to_specifier_set`` round-tripping.

The conversion is partial (not every range is specifier-expressible),
but when it succeeds it must round-trip exactly. ``None`` is allowed;
silent semantic drift is not.
"""

from __future__ import annotations

from functools import reduce
from typing import TYPE_CHECKING

import pytest
from hypothesis import given

from packaging.ranges import VersionRange

from .strategies import SETTINGS, specifier_sets

if TYPE_CHECKING:
    from packaging.specifiers import SpecifierSet

pytestmark = pytest.mark.property


@given(spec_set=specifier_sets())
@SETTINGS
def test_specifier_derived_ranges_always_have_a_specifier_set(
    spec_set: SpecifierSet,
) -> None:
    """Specifier-derived ranges always re-encode (incl. ``<0`` for empty)."""
    r = VersionRange.from_specifier_set(spec_set)
    converted = r.to_specifier_set()
    assert converted is not None, (
        f"specifier-derived range {r!r} should always re-encode "
        f"(input was {spec_set!r})"
    )
    assert VersionRange.from_specifier_set(converted) == r


@given(spec_set=specifier_sets())
@SETTINGS
def test_to_specifier_sets_round_trips_when_not_none(
    spec_set: SpecifierSet,
) -> None:
    """If ``to_specifier_sets`` succeeds, the union of its elements equals ``r``."""
    r = VersionRange.from_specifier_set(spec_set)
    converted = r.to_specifier_sets()
    if converted is None:
        return
    assert converted, "to_specifier_sets must return a non-empty tuple"
    union = reduce(
        VersionRange.union,
        (VersionRange.from_specifier_set(s) for s in converted),
    )
    assert union == r


@given(a=specifier_sets(), b=specifier_sets())
@SETTINGS
def test_intersection_round_trips_when_not_none(
    a: SpecifierSet, b: SpecifierSet
) -> None:
    """SpecifierSet is closed under intersection."""
    ra = VersionRange.from_specifier_set(a)
    rb = VersionRange.from_specifier_set(b)
    inter = ra & rb
    converted = inter.to_specifier_set()
    assert converted is not None
    assert VersionRange.from_specifier_set(converted) == inter


@given(a=specifier_sets(), b=specifier_sets())
@SETTINGS
def test_to_specifier_sets_handles_union_when_intervals_are_specifier_shaped(
    a: SpecifierSet, b: SpecifierSet
) -> None:
    """Per-interval encoding succeeds for unions of specifier-derived ranges."""
    ra = VersionRange.from_specifier_set(a)
    rb = VersionRange.from_specifier_set(b)
    u = ra | rb
    converted = u.to_specifier_sets()
    assert converted is not None
    union = reduce(
        VersionRange.union,
        (VersionRange.from_specifier_set(s) for s in converted),
    )
    assert union == u


@given(spec_set=specifier_sets())
@SETTINGS
def test_to_specifier_set_implies_to_specifier_sets(
    spec_set: SpecifierSet,
) -> None:
    """``to_specifier_set is not None`` ⇒ ``to_specifier_sets is not None``."""
    r = VersionRange.from_specifier_set(spec_set)
    if r.to_specifier_set() is not None:
        assert r.to_specifier_sets() is not None


@given(spec_set=specifier_sets())
@SETTINGS
def test_complement_round_trips_or_returns_none(spec_set: SpecifierSet) -> None:
    """The complement of a specifier-derived range is often not
    specifier-expressible (e.g. ``~(>=1,<2)`` is two disjoint intervals).
    Exercises the partial-conversion contract: ``to_specifier_set`` either
    returns ``None`` or round-trips exactly, never drifting."""
    r = VersionRange.from_specifier_set(spec_set).complement()
    converted = r.to_specifier_set()
    if converted is not None:
        assert VersionRange.from_specifier_set(converted) == r
