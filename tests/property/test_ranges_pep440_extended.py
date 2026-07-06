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

from .strategies import (
    SETTINGS,
    VERSION_POOL,
    rich_specifier_sets,
)

if TYPE_CHECKING:
    from packaging.ranges import VersionRange as _VersionRange
    from packaging.specifiers import SpecifierSet

pytestmark = pytest.mark.property

# Extra boundary probes for the membership oracle. The minimal engine
# canonicalizes empty and ``MIN_VERSION`` regions (e.g. ``(1.dev1+, 1.dev2)``
# collapses to ``(empty)``, ``0.dev0`` lower bounds collapse to ``-inf``), so
# complement-bearing laws can differ in bound representation while accepting
# the same versions. These probes plus ``VERSION_POOL`` distinguish any
# genuine version-set difference.
_BOUNDARY_PROBES = [
    "0.dev0",
    "0.dev1",
    "1.dev0",
    "1.dev1",
    "1.dev2",
    "0rc0.dev0",
    "0rc0.dev1",
    "2.dev0",
    "1!0.dev0",
]


_ARBITRARY_PROBES = ["garbage", "unparsable", "not-a-version", "wat"]


def _version_eq(a: _VersionRange, b: _VersionRange) -> bool:
    """``a`` and ``b`` accept the same *versions* and ``===`` literals.

    Probes cover ``VERSION_POOL``, dev/MIN_VERSION boundary versions, and
    every ``===`` literal admitted or rejected by either operand, but not
    free non-version strings: the ``_admit_arbitrary`` slot attaches only to
    the genuine universal range, so ``r | ~r`` covers every version yet never
    admits arbitrary strings the way ``full()`` does. Genuine differences in
    bounds or literal slots are caught; benign empty/MIN_VERSION bound
    canonicalization and the ``_admit_arbitrary`` asymmetry are not.
    """
    literals = a._admit | a._reject | b._admit | b._reject
    probes = [str(v) for v in VERSION_POOL] + _BOUNDARY_PROBES + list(literals)
    return all((p in a) == (p in b) for p in probes)


def _mem_eq(a: _VersionRange, b: _VersionRange) -> bool:
    """``a`` and ``b`` accept the same items, including non-version strings.

    Extends :func:`_version_eq` with free non-version probes, so it also
    distinguishes the ``_admit_arbitrary`` slot. Use for laws that do not
    compare against ``full()``.
    """
    if not _version_eq(a, b):
        return False
    return all((p in a) == (p in b) for p in _ARBITRARY_PROBES)


@given(spec_set=rich_specifier_sets())
@SETTINGS
def test_double_complement_identity_rich(spec_set: SpecifierSet) -> None:
    r = spec_set.to_range()
    # Involution holds on the version set. The minimal engine canonicalizes
    # a ``MIN_VERSION`` (``0.dev0``) lower bound to ``-inf`` (no version is
    # below it), so ``~~r`` can differ from ``r`` only in bound
    # representation, never in which versions it accepts (e.g. ``==0.*``);
    # compare on the version subset.
    assert _mem_eq(r.complement().complement(), r)


@given(spec_set=rich_specifier_sets())
@SETTINGS
def test_complement_partitions_rich(spec_set: SpecifierSet) -> None:
    r = spec_set.to_range()
    c = r.complement()
    assert _mem_eq(r.intersection(c), VersionRange.empty())
    assert _version_eq(r.union(c), VersionRange.full())


@given(a=rich_specifier_sets(), b=rich_specifier_sets())
@SETTINGS
def test_de_morgan_intersect_rich(a: SpecifierSet, b: SpecifierSet) -> None:
    ra = a.to_range()
    rb = b.to_range()
    # The minimal engine canonicalizes empty/MIN_VERSION regions, so the two
    # sides can differ in bound representation; compare on the version set.
    assert _mem_eq(
        ra.intersection(rb).complement(),
        ra.complement().union(rb.complement()),
    )


@given(a=rich_specifier_sets(), b=rich_specifier_sets())
@SETTINGS
def test_de_morgan_union_rich(a: SpecifierSet, b: SpecifierSet) -> None:
    ra = a.to_range()
    rb = b.to_range()
    assert _mem_eq(
        ra.union(rb).complement(),
        ra.complement().intersection(rb.complement()),
    )


@given(spec_set=rich_specifier_sets())
@SETTINGS
def test_idempotence_rich(spec_set: SpecifierSet) -> None:
    r = spec_set.to_range()
    assert r.union(r) == r
    assert r.intersection(r) == r


@given(a=rich_specifier_sets(), b=rich_specifier_sets())
@SETTINGS
def test_intersect_commutative_rich(a: SpecifierSet, b: SpecifierSet) -> None:
    ra = a.to_range()
    rb = b.to_range()
    assert ra.intersection(rb) == rb.intersection(ra)


@given(a=rich_specifier_sets(), b=rich_specifier_sets())
@SETTINGS
def test_union_commutative_rich(a: SpecifierSet, b: SpecifierSet) -> None:
    ra = a.to_range()
    rb = b.to_range()
    assert ra.union(rb) == rb.union(ra)


@given(a=rich_specifier_sets(), b=rich_specifier_sets(), c=rich_specifier_sets())
@SETTINGS
def test_intersect_associative_rich(
    a: SpecifierSet, b: SpecifierSet, c: SpecifierSet
) -> None:
    ra = a.to_range()
    rb = b.to_range()
    rc = c.to_range()
    assert ra.intersection(rb).intersection(rc) == ra.intersection(rb.intersection(rc))


@given(a=rich_specifier_sets(), b=rich_specifier_sets(), c=rich_specifier_sets())
@SETTINGS
def test_union_associative_rich(
    a: SpecifierSet, b: SpecifierSet, c: SpecifierSet
) -> None:
    ra = a.to_range()
    rb = b.to_range()
    rc = c.to_range()
    assert ra.union(rb).union(rc) == ra.union(rb.union(rc))


@given(a=rich_specifier_sets(), b=rich_specifier_sets(), c=rich_specifier_sets())
@SETTINGS
def test_intersect_distributes_over_union_rich(
    a: SpecifierSet, b: SpecifierSet, c: SpecifierSet
) -> None:
    ra = a.to_range()
    rb = b.to_range()
    rc = c.to_range()
    assert ra.intersection(rb.union(rc)) == ra.intersection(rb).union(
        ra.intersection(rc)
    )


@given(a=rich_specifier_sets(), b=rich_specifier_sets(), c=rich_specifier_sets())
@SETTINGS
def test_union_distributes_over_intersect_rich(
    a: SpecifierSet, b: SpecifierSet, c: SpecifierSet
) -> None:
    ra = a.to_range()
    rb = b.to_range()
    rc = c.to_range()
    assert ra.union(rb.intersection(rc)) == ra.union(rb).intersection(ra.union(rc))


@given(spec_set=rich_specifier_sets())
@SETTINGS
def test_membership_consistent_with_complement_rich(
    spec_set: SpecifierSet,
) -> None:
    r = spec_set.to_range()
    c = r.complement()
    for v in VERSION_POOL:
        assert (v in c) == (v not in r)


@given(a=rich_specifier_sets(), b=rich_specifier_sets())
@SETTINGS
def test_membership_consistent_with_intersect_rich(
    a: SpecifierSet, b: SpecifierSet
) -> None:
    ra = a.to_range()
    rb = b.to_range()
    inter = ra.intersection(rb)
    for v in VERSION_POOL:
        assert (v in inter) == ((v in ra) and (v in rb))


@given(a=rich_specifier_sets(), b=rich_specifier_sets())
@SETTINGS
def test_membership_consistent_with_union_rich(
    a: SpecifierSet, b: SpecifierSet
) -> None:
    ra = a.to_range()
    rb = b.to_range()
    union = ra.union(rb)
    for v in VERSION_POOL:
        assert (v in union) == ((v in ra) or (v in rb))


@given(spec_set=rich_specifier_sets(include_arbitrary=True))
@SETTINGS
def test_double_complement_with_arbitrary(spec_set: SpecifierSet) -> None:
    r = spec_set.to_range()
    # Involution holds on the accepted set. The minimal engine canonicalizes
    # a ``MIN_VERSION`` (``0.dev0``) lower bound to ``-inf`` (no version is
    # below it), so ``~~r`` can differ from ``r`` only in bound
    # representation, never in which items it accepts; compare on the
    # probe sample (versions plus ``===`` literals).
    assert _mem_eq(r.complement().complement(), r)


@given(spec_set=rich_specifier_sets(include_arbitrary=True))
@SETTINGS
def test_complement_partitions_with_arbitrary(spec_set: SpecifierSet) -> None:
    r = spec_set.to_range()
    c = r.complement()
    assert _mem_eq(r.intersection(c), VersionRange.empty())
    assert _version_eq(r.union(c), VersionRange.full())


@given(
    a=rich_specifier_sets(include_arbitrary=True),
    b=rich_specifier_sets(include_arbitrary=True),
)
@SETTINGS
def test_de_morgan_intersect_with_arbitrary(a: SpecifierSet, b: SpecifierSet) -> None:
    ra = a.to_range()
    rb = b.to_range()
    # The minimal engine canonicalizes empty/MIN_VERSION regions, so the two
    # sides can differ in bound representation; compare on the probe sample.
    assert _mem_eq(
        ra.intersection(rb).complement(),
        ra.complement().union(rb.complement()),
    )


@given(
    a=rich_specifier_sets(include_arbitrary=True),
    b=rich_specifier_sets(include_arbitrary=True),
)
@SETTINGS
def test_de_morgan_union_with_arbitrary(a: SpecifierSet, b: SpecifierSet) -> None:
    ra = a.to_range()
    rb = b.to_range()
    assert _mem_eq(
        ra.union(rb).complement(),
        ra.complement().intersection(rb.complement()),
    )


@given(spec_set=rich_specifier_sets(include_arbitrary=True))
@SETTINGS
def test_idempotence_with_arbitrary(spec_set: SpecifierSet) -> None:
    r = spec_set.to_range()
    assert r.union(r) == r
    assert r.intersection(r) == r


@given(spec_set=rich_specifier_sets(include_arbitrary=True))
@SETTINGS
def test_membership_consistent_with_complement_arbitrary(
    spec_set: SpecifierSet,
) -> None:
    r = spec_set.to_range()
    c = r.complement()
    for v in VERSION_POOL:
        assert (v in c) == (v not in r)
