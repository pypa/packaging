# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.

"""Property tests for ``VersionRange`` Boolean lattice laws.

Identity, idempotence, commutativity, associativity, distributivity,
double-complement, De Morgan, and consistency with ``__contains__``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from hypothesis import given

from packaging.ranges import VersionRange
from packaging.specifiers import SpecifierSet

from .strategies import (
    SETTINGS,
    VERSION_POOL,
    eq_versions_only,
    pep440_versions,
    rich_specifier_sets,
    specifier_sets,
)

if TYPE_CHECKING:
    from packaging.version import Version

pytestmark = pytest.mark.property


def _to_range(spec_set: SpecifierSet) -> VersionRange:
    """Lift a non-``===`` SpecifierSet into a VersionRange."""
    return spec_set.to_range()


@given(spec_set=specifier_sets())
@SETTINGS
def test_intersect_with_unbounded_is_identity(spec_set: SpecifierSet) -> None:
    r = _to_range(spec_set)
    u = VersionRange.full()
    assert r.intersection(u) == r
    assert u.intersection(r) == r


@given(spec_set=specifier_sets())
@SETTINGS
def test_union_with_empty_is_identity(spec_set: SpecifierSet) -> None:
    r = _to_range(spec_set)
    e = VersionRange.empty()
    assert r.union(e) == r
    assert e.union(r) == r


@given(spec_set=specifier_sets())
@SETTINGS
def test_intersect_with_empty_is_empty(spec_set: SpecifierSet) -> None:
    r = _to_range(spec_set)
    e = VersionRange.empty()
    assert r.intersection(e) == e
    assert e.intersection(r) == e


@given(spec_set=specifier_sets())
@SETTINGS
def test_union_with_unbounded_is_unbounded(spec_set: SpecifierSet) -> None:
    r = _to_range(spec_set)
    u = VersionRange.full()
    assert r.union(u) == u
    assert u.union(r) == u


@given(spec_set=specifier_sets())
@SETTINGS
def test_idempotence(spec_set: SpecifierSet) -> None:
    r = _to_range(spec_set)
    assert r.union(r) == r
    assert r.intersection(r) == r


@given(a=specifier_sets(), b=specifier_sets())
@SETTINGS
def test_union_commutative(a: SpecifierSet, b: SpecifierSet) -> None:
    ra, rb = _to_range(a), _to_range(b)
    assert ra.union(rb) == rb.union(ra)


@given(a=specifier_sets(), b=specifier_sets())
@SETTINGS
def test_intersect_commutative(a: SpecifierSet, b: SpecifierSet) -> None:
    ra, rb = _to_range(a), _to_range(b)
    assert ra.intersection(rb) == rb.intersection(ra)


@given(a=specifier_sets(), b=specifier_sets(), c=specifier_sets())
@SETTINGS
def test_union_associative(a: SpecifierSet, b: SpecifierSet, c: SpecifierSet) -> None:
    ra, rb, rc = _to_range(a), _to_range(b), _to_range(c)
    assert ra.union(rb).union(rc) == ra.union(rb.union(rc))


@given(a=specifier_sets(), b=specifier_sets(), c=specifier_sets())
@SETTINGS
def test_intersect_associative(
    a: SpecifierSet, b: SpecifierSet, c: SpecifierSet
) -> None:
    ra, rb, rc = _to_range(a), _to_range(b), _to_range(c)
    assert ra.intersection(rb).intersection(rc) == ra.intersection(rb.intersection(rc))


@given(spec_set=specifier_sets())
@SETTINGS
def test_double_complement_identity(spec_set: SpecifierSet) -> None:
    r = _to_range(spec_set)
    # Complement preserves every membership slot, so involution holds
    # structurally.
    assert r.complement().complement() == r


@given(spec_set=specifier_sets())
@SETTINGS
def test_complement_partitions(spec_set: SpecifierSet) -> None:
    r = _to_range(spec_set)
    c = r.complement()
    # r and ~r are disjoint and together cover every version. Compare on
    # the version subset: ``_admit_arbitrary`` only attaches to the
    # genuine universal range, so ``r | ~r`` never carries it when
    # neither side is empty.
    assert r.intersection(c).is_empty
    assert eq_versions_only(r.union(c), VersionRange.full())


@given(a=specifier_sets(), b=specifier_sets())
@SETTINGS
def test_de_morgan_intersect(a: SpecifierSet, b: SpecifierSet) -> None:
    ra, rb = _to_range(a), _to_range(b)
    # ``specifier_sets`` never produces the universal set, so both sides
    # stay in the PEP 440 universe and De Morgan holds structurally.
    assert (ra.intersection(rb)).complement() == ra.complement().union(rb.complement())


@given(a=specifier_sets(), b=specifier_sets())
@SETTINGS
def test_de_morgan_union(a: SpecifierSet, b: SpecifierSet) -> None:
    ra, rb = _to_range(a), _to_range(b)
    assert (ra.union(rb)).complement() == ra.complement().intersection(rb.complement())


@given(a=specifier_sets(), b=specifier_sets(), c=specifier_sets())
@SETTINGS
def test_intersect_distributes_over_union(
    a: SpecifierSet, b: SpecifierSet, c: SpecifierSet
) -> None:
    ra, rb, rc = _to_range(a), _to_range(b), _to_range(c)
    lhs = ra.intersection(rb.union(rc))
    rhs = ra.intersection(rb).union(ra.intersection(rc))
    assert lhs == rhs


@given(a=specifier_sets(), b=specifier_sets(), c=specifier_sets())
@SETTINGS
def test_union_distributes_over_intersect(
    a: SpecifierSet, b: SpecifierSet, c: SpecifierSet
) -> None:
    ra, rb, rc = _to_range(a), _to_range(b), _to_range(c)
    lhs = ra.union(rb.intersection(rc))
    rhs = ra.union(rb).intersection(ra.union(rc))
    assert lhs == rhs


@given(spec_set=specifier_sets())
@SETTINGS
def test_operator_aliases(spec_set: SpecifierSet) -> None:
    """Operators mirror the named methods."""
    r = _to_range(spec_set)
    other = _to_range(SpecifierSet(">=1.0,<2.0"))
    assert (r & other) == r.intersection(other)
    assert (r | other) == r.union(other)
    assert (~r) == r.complement()


@given(a=specifier_sets(), b=specifier_sets())
@SETTINGS
def test_membership_consistent_with_intersect(a: SpecifierSet, b: SpecifierSet) -> None:
    """``v in (a & b)`` iff ``v in a`` AND ``v in b`` for every version."""
    ra, rb = _to_range(a), _to_range(b)
    intersection = ra.intersection(rb)
    for v in VERSION_POOL:
        assert (v in intersection) == ((v in ra) and (v in rb))


@given(a=specifier_sets(), b=specifier_sets())
@SETTINGS
def test_membership_consistent_with_union(a: SpecifierSet, b: SpecifierSet) -> None:
    """``v in (a | b)`` iff ``v in a`` OR ``v in b`` for every version."""
    ra, rb = _to_range(a), _to_range(b)
    union = ra.union(rb)
    for v in VERSION_POOL:
        assert (v in union) == ((v in ra) or (v in rb))


@given(spec_set=specifier_sets())
@SETTINGS
def test_membership_consistent_with_complement(spec_set: SpecifierSet) -> None:
    """``v in ~r`` iff ``v not in r`` for every version."""
    r = _to_range(spec_set)
    c = r.complement()
    for v in VERSION_POOL:
        assert (v in c) == (v not in r)


@given(spec_set=specifier_sets())
@SETTINGS
def test_exact_singleton_membership(spec_set: SpecifierSet) -> None:
    """``VersionRange.singleton(v)`` contains only ``v`` and no other version."""
    r = _to_range(spec_set)
    for v in VERSION_POOL:
        exact = VersionRange.singleton(v)
        assert v in exact
        # ``v`` is in (r & exact) iff v in r.
        assert (v in r.intersection(exact)) == (v in r)


@given(spec_set=specifier_sets())
@SETTINGS
def test_hash_equality_consistency(spec_set: SpecifierSet) -> None:
    """Equal ranges have equal hashes; usable as dict/set keys."""
    r1 = _to_range(spec_set)
    r2 = _to_range(spec_set)
    assert r1 == r2
    assert hash(r1) == hash(r2)


@given(spec_set=specifier_sets())
@SETTINGS
def test_complement_is_empty_iff_unbounded(spec_set: SpecifierSet) -> None:
    """``~r`` is empty exactly when ``r`` covers every version.

    Compares on the version subset only: a ``>=0.dev0``-derived range
    reaches FULL_RANGE bounds but does not admit arbitrary strings, so its
    complement is empty even though it is not structurally equal to
    ``VersionRange.full()``.
    """
    r = _to_range(spec_set)
    if r.complement().is_empty:
        assert eq_versions_only(r, VersionRange.full())
    if eq_versions_only(r, VersionRange.full()):
        assert r.complement().is_empty


@given(versions=specifier_sets(), v=pep440_versions())
@SETTINGS
def test_exact_equals_singleton_intersection(
    versions: SpecifierSet, v: Version
) -> None:
    """``r & exact(v)`` is non-empty iff v is in r, and equals exact(v) when so."""
    r = _to_range(versions)
    e = VersionRange.singleton(v)
    inter = r.intersection(e)
    if v in r:
        assert inter == e
    else:
        assert inter.is_empty


@given(spec_set=rich_specifier_sets())
@SETTINGS
def test_full_range_is_identity_for_filter(spec_set: SpecifierSet) -> None:
    """``full()`` is the identity for ``&`` w.r.t. filtering.

    Pre-release eligibility rides on ``_prereleases``, which ``==`` and
    ``__contains__`` ignore by design, so the structural laws above can't see
    it; only ``filter`` does. Folding ``full() & r1 & r2 & ...`` must never
    erase a range's tag.
    """
    r = spec_set.to_range()
    full = VersionRange.full()
    expected = list(r.filter(VERSION_POOL))
    assert list((r & full).filter(VERSION_POOL)) == expected
    assert list((full & r).filter(VERSION_POOL)) == expected


@given(a=rich_specifier_sets(), b=rich_specifier_sets())
@SETTINGS
def test_intersection_filter_matches_merged_set(
    a: SpecifierSet, b: SpecifierSet
) -> None:
    """``to_range`` is a homomorphism w.r.t. filtering.

    ``(a.to_range() & b.to_range()).filter`` equals
    ``(a & b).to_range().filter``, including pre-release eligibility (which
    the structural ``==`` laws above cannot observe).
    """
    composed = list((a.to_range() & b.to_range()).filter(VERSION_POOL))
    merged = list((a & b).to_range().filter(VERSION_POOL))
    assert composed == merged


@given(spec_set=rich_specifier_sets(include_arbitrary=True))
@SETTINGS
def test_to_range_filter_and_contains_mirror_specifier_set(
    spec_set: SpecifierSet,
) -> None:
    """``filter`` and ``__contains__`` on the range mirror the originating set.

    Closes the gap that the bounds-only fast path in ``SpecifierSet.filter``
    might diverge from ``VersionRange.filter`` on the ``prereleases=None``
    default, or that ``v in to_range()`` might drift from ``v in spec_set``.
    """
    r = spec_set.to_range()
    pool = [str(v) for v in VERSION_POOL] + ["unparsable", "garbage"]
    for prereleases in (None, True, False):
        assert list(r.filter(pool, prereleases=prereleases)) == list(
            spec_set.filter(pool, prereleases=prereleases)
        )
    for item in pool:
        assert (item in r) == (item in spec_set)


@given(spec_set=rich_specifier_sets(include_arbitrary=True))
@SETTINGS
def test_unsatisfiable_implies_no_pool_match(spec_set: SpecifierSet) -> None:
    """A set flagged unsatisfiable can satisfy nothing under the same policy.

    Pinned to ``prereleases=False`` to exercise the prerelease-only branch
    that ``is_unsatisfiable`` consults; the implication is sound for any
    policy.
    """
    pinned = SpecifierSet(str(spec_set), prereleases=False)
    if pinned.is_unsatisfiable():
        assert not any(pinned.contains(v) for v in VERSION_POOL)


# Omitted: test_prerelease_only_implies_all_matches_are_prereleases relied on
# the dropped ``VersionRange.is_prerelease_only`` property.


@given(spec_set=specifier_sets(vary_prereleases=True))
@SETTINGS
def test_identity_laws_under_each_policy(spec_set: SpecifierSet) -> None:
    """``full``/``empty`` stamped with the same policy obey the four identities.

    Stamps ``full()``/``empty()`` with the same configured policy as the
    drawn range so ``_check_policy_compat`` accepts the pair, then asserts
    the four lattice identities under the version-only oracle (the
    universal-range arbitrary-string slot does not survive intersection).
    """
    r = spec_set.to_range()
    p = r._prereleases_configured
    full = VersionRange.full(prereleases=p)
    empty = VersionRange.empty(prereleases=p)
    assert eq_versions_only(r & full, r)
    assert eq_versions_only(r | empty, r)
    assert r & empty == empty
    assert eq_versions_only(r | full, full)


@given(spec_set=specifier_sets(vary_prereleases=True))
@SETTINGS
def test_idempotence_under_each_policy(spec_set: SpecifierSet) -> None:
    """``r & r == r`` and ``r | r == r`` for every configured policy."""
    r = spec_set.to_range()
    assert r & r == r
    assert r | r == r
