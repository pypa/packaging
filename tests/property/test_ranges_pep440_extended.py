# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.

"""Set-algebra invariants re-run on the full PEP 440 specifier surface.

Uses :func:`tests.property.strategies.rich_specifier_sets`, which
adds wildcards, ``~=``, locals, pre/post/dev RHS, epochs, multi-
segment release tuples, and optionally ``===``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from hypothesis import given

from packaging.ranges import VersionRange

from .strategies import SETTINGS, VERSION_POOL, rich_specifier_sets

if TYPE_CHECKING:
    from packaging.specifiers import SpecifierSet

pytestmark = pytest.mark.property


@given(spec_set=rich_specifier_sets())
@SETTINGS
def test_double_complement_identity_rich(spec_set: SpecifierSet) -> None:
    r = VersionRange.from_specifier_set(spec_set)
    assert r.complement().complement() == r


@given(spec_set=rich_specifier_sets())
@SETTINGS
def test_complement_partitions_rich(spec_set: SpecifierSet) -> None:
    r = VersionRange.from_specifier_set(spec_set)
    c = r.complement()
    assert r.intersection(c).is_empty
    assert r.union(c) == VersionRange.full()


@given(a=rich_specifier_sets(), b=rich_specifier_sets())
@SETTINGS
def test_de_morgan_intersect_rich(a: SpecifierSet, b: SpecifierSet) -> None:
    ra = VersionRange.from_specifier_set(a)
    rb = VersionRange.from_specifier_set(b)
    assert ra.intersection(rb).complement() == ra.complement().union(rb.complement())


@given(a=rich_specifier_sets(), b=rich_specifier_sets())
@SETTINGS
def test_de_morgan_union_rich(a: SpecifierSet, b: SpecifierSet) -> None:
    ra = VersionRange.from_specifier_set(a)
    rb = VersionRange.from_specifier_set(b)
    assert ra.union(rb).complement() == ra.complement().intersection(rb.complement())


@given(spec_set=rich_specifier_sets())
@SETTINGS
def test_idempotence_rich(spec_set: SpecifierSet) -> None:
    r = VersionRange.from_specifier_set(spec_set)
    assert r.union(r) == r
    assert r.intersection(r) == r


@given(a=rich_specifier_sets(), b=rich_specifier_sets())
@SETTINGS
def test_intersect_commutative_rich(a: SpecifierSet, b: SpecifierSet) -> None:
    ra = VersionRange.from_specifier_set(a)
    rb = VersionRange.from_specifier_set(b)
    assert ra.intersection(rb) == rb.intersection(ra)


@given(a=rich_specifier_sets(), b=rich_specifier_sets())
@SETTINGS
def test_union_commutative_rich(a: SpecifierSet, b: SpecifierSet) -> None:
    ra = VersionRange.from_specifier_set(a)
    rb = VersionRange.from_specifier_set(b)
    assert ra.union(rb) == rb.union(ra)


@given(a=rich_specifier_sets(), b=rich_specifier_sets(), c=rich_specifier_sets())
@SETTINGS
def test_intersect_associative_rich(
    a: SpecifierSet, b: SpecifierSet, c: SpecifierSet
) -> None:
    ra = VersionRange.from_specifier_set(a)
    rb = VersionRange.from_specifier_set(b)
    rc = VersionRange.from_specifier_set(c)
    assert ra.intersection(rb).intersection(rc) == ra.intersection(rb.intersection(rc))


@given(a=rich_specifier_sets(), b=rich_specifier_sets(), c=rich_specifier_sets())
@SETTINGS
def test_union_associative_rich(
    a: SpecifierSet, b: SpecifierSet, c: SpecifierSet
) -> None:
    ra = VersionRange.from_specifier_set(a)
    rb = VersionRange.from_specifier_set(b)
    rc = VersionRange.from_specifier_set(c)
    assert ra.union(rb).union(rc) == ra.union(rb.union(rc))


@given(a=rich_specifier_sets(), b=rich_specifier_sets(), c=rich_specifier_sets())
@SETTINGS
def test_intersect_distributes_over_union_rich(
    a: SpecifierSet, b: SpecifierSet, c: SpecifierSet
) -> None:
    ra = VersionRange.from_specifier_set(a)
    rb = VersionRange.from_specifier_set(b)
    rc = VersionRange.from_specifier_set(c)
    assert ra.intersection(rb.union(rc)) == ra.intersection(rb).union(
        ra.intersection(rc)
    )


@given(a=rich_specifier_sets(), b=rich_specifier_sets(), c=rich_specifier_sets())
@SETTINGS
def test_union_distributes_over_intersect_rich(
    a: SpecifierSet, b: SpecifierSet, c: SpecifierSet
) -> None:
    ra = VersionRange.from_specifier_set(a)
    rb = VersionRange.from_specifier_set(b)
    rc = VersionRange.from_specifier_set(c)
    assert ra.union(rb.intersection(rc)) == ra.union(rb).intersection(ra.union(rc))


@given(spec_set=rich_specifier_sets())
@SETTINGS
def test_membership_consistent_with_complement_rich(
    spec_set: SpecifierSet,
) -> None:
    r = VersionRange.from_specifier_set(spec_set)
    c = r.complement()
    for v in VERSION_POOL:
        assert (v in c) == (v not in r)


@given(a=rich_specifier_sets(), b=rich_specifier_sets())
@SETTINGS
def test_membership_consistent_with_intersect_rich(
    a: SpecifierSet, b: SpecifierSet
) -> None:
    ra = VersionRange.from_specifier_set(a)
    rb = VersionRange.from_specifier_set(b)
    inter = ra.intersection(rb)
    for v in VERSION_POOL:
        assert (v in inter) == ((v in ra) and (v in rb))


@given(a=rich_specifier_sets(), b=rich_specifier_sets())
@SETTINGS
def test_membership_consistent_with_union_rich(
    a: SpecifierSet, b: SpecifierSet
) -> None:
    ra = VersionRange.from_specifier_set(a)
    rb = VersionRange.from_specifier_set(b)
    union = ra.union(rb)
    for v in VERSION_POOL:
        assert (v in union) == ((v in ra) or (v in rb))


@given(spec_set=rich_specifier_sets(include_arbitrary=True))
@SETTINGS
def test_double_complement_with_arbitrary(spec_set: SpecifierSet) -> None:
    r = VersionRange.from_specifier_set(spec_set)
    assert r.complement().complement() == r


@given(spec_set=rich_specifier_sets(include_arbitrary=True))
@SETTINGS
def test_complement_partitions_with_arbitrary(spec_set: SpecifierSet) -> None:
    r = VersionRange.from_specifier_set(spec_set)
    c = r.complement()
    assert r.intersection(c).is_empty
    assert r.union(c) == VersionRange.full()


@given(
    a=rich_specifier_sets(include_arbitrary=True),
    b=rich_specifier_sets(include_arbitrary=True),
)
@SETTINGS
def test_de_morgan_intersect_with_arbitrary(a: SpecifierSet, b: SpecifierSet) -> None:
    ra = VersionRange.from_specifier_set(a)
    rb = VersionRange.from_specifier_set(b)
    assert ra.intersection(rb).complement() == ra.complement().union(rb.complement())


@given(
    a=rich_specifier_sets(include_arbitrary=True),
    b=rich_specifier_sets(include_arbitrary=True),
)
@SETTINGS
def test_de_morgan_union_with_arbitrary(a: SpecifierSet, b: SpecifierSet) -> None:
    ra = VersionRange.from_specifier_set(a)
    rb = VersionRange.from_specifier_set(b)
    assert ra.union(rb).complement() == ra.complement().intersection(rb.complement())


@given(spec_set=rich_specifier_sets(include_arbitrary=True))
@SETTINGS
def test_idempotence_with_arbitrary(spec_set: SpecifierSet) -> None:
    r = VersionRange.from_specifier_set(spec_set)
    assert r.union(r) == r
    assert r.intersection(r) == r


@given(spec_set=rich_specifier_sets(include_arbitrary=True))
@SETTINGS
def test_membership_consistent_with_complement_arbitrary(
    spec_set: SpecifierSet,
) -> None:
    r = VersionRange.from_specifier_set(spec_set)
    c = r.complement()
    for v in VERSION_POOL:
        assert (v in c) == (v not in r)
