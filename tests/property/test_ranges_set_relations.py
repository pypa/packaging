# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.

"""Property tests for ``is_subset`` / ``is_superset`` / ``is_disjoint``.

Each relation is pinned to its set-algebra definition (the oracle the methods
optimize): ``is_disjoint`` to ``(a & b).is_empty`` and ``is_subset`` to
``(a & ~b).is_empty``. The plain strategy exercises the bounds-only fast path;
the ``===`` strategy forces the algebra fallback, so the same oracle guards
both code paths. Pointwise-membership and symmetry round out the checks.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from hypothesis import given

from packaging.ranges import VersionRange

from .strategies import (
    SETTINGS,
    VERSION_POOL,
    rich_specifier_sets,
    specifier_sets,
)

if TYPE_CHECKING:
    from packaging.specifiers import SpecifierSet

pytestmark = pytest.mark.property


@given(a=specifier_sets(), b=specifier_sets())
@SETTINGS
def test_disjoint_matches_algebra_plain(a: SpecifierSet, b: SpecifierSet) -> None:
    ra, rb = a.to_range(), b.to_range()
    assert ra.is_disjoint(rb) == (ra & rb).is_empty


@given(a=specifier_sets(), b=specifier_sets())
@SETTINGS
def test_subset_matches_algebra_plain(a: SpecifierSet, b: SpecifierSet) -> None:
    ra, rb = a.to_range(), b.to_range()
    assert ra.is_subset(rb) == (ra & ~rb).is_empty


@given(
    a=rich_specifier_sets(include_arbitrary=True),
    b=rich_specifier_sets(include_arbitrary=True),
)
@SETTINGS
def test_disjoint_matches_algebra_rich(a: SpecifierSet, b: SpecifierSet) -> None:
    """``===`` ranges defer to the algebra; ``_is_plain`` must gate them out."""
    ra, rb = a.to_range(), b.to_range()
    assert ra.is_disjoint(rb) == (ra & rb).is_empty


@given(
    a=rich_specifier_sets(include_arbitrary=True),
    b=rich_specifier_sets(include_arbitrary=True),
)
@SETTINGS
def test_subset_matches_algebra_rich(a: SpecifierSet, b: SpecifierSet) -> None:
    """``===`` ranges defer to the algebra; ``_is_plain`` must gate them out."""
    ra, rb = a.to_range(), b.to_range()
    assert ra.is_subset(rb) == (ra & ~rb).is_empty


@given(a=specifier_sets(), b=specifier_sets())
@SETTINGS
def test_superset_is_subset_mirror(a: SpecifierSet, b: SpecifierSet) -> None:
    ra, rb = a.to_range(), b.to_range()
    assert ra.is_superset(rb) == rb.is_subset(ra)


@given(a=specifier_sets(), b=specifier_sets())
@SETTINGS
def test_disjoint_symmetric(a: SpecifierSet, b: SpecifierSet) -> None:
    ra, rb = a.to_range(), b.to_range()
    assert ra.is_disjoint(rb) == rb.is_disjoint(ra)


@given(spec_set=specifier_sets())
@SETTINGS
def test_subset_and_superset_reflexive(spec_set: SpecifierSet) -> None:
    r = spec_set.to_range()
    assert r.is_subset(r)
    assert r.is_superset(r)


@given(a=specifier_sets(), b=specifier_sets())
@SETTINGS
def test_intersection_is_subset_and_pointwise(a: SpecifierSet, b: SpecifierSet) -> None:
    """``a & b`` is a subset of each operand, with consistent membership.

    Two independently drawn ranges are rarely a subset pair, so the
    intersection (always contained in each operand) drives the True branch
    in every example. Pointwise membership over the pool must agree.
    """
    ra, rb = a.to_range(), b.to_range()
    inter = ra & rb
    assert inter.is_subset(ra)
    assert inter.is_subset(rb)
    assert all(v in ra and v in rb for v in VERSION_POOL if v in inter)


@given(a=specifier_sets(), b=specifier_sets())
@SETTINGS
def test_disjoint_implies_no_shared_member(a: SpecifierSet, b: SpecifierSet) -> None:
    ra, rb = a.to_range(), b.to_range()
    if ra.is_disjoint(rb):
        assert not any(v in ra and v in rb for v in VERSION_POOL)


@given(spec_set=specifier_sets())
@SETTINGS
def test_empty_is_subset_and_disjoint(spec_set: SpecifierSet) -> None:
    r = spec_set.to_range()
    assert VersionRange.empty().is_subset(r)
    assert VersionRange.empty().is_disjoint(r)
