# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.

"""Property tests for ``VersionRange`` algebra across distinct epochs.

PEP 440 epochs partition the version order into disjoint cohorts; an
``==1.0`` predicate in epoch 0 never overlaps an ``==1.0`` predicate in
epoch 1. The lattice laws still hold across cohorts.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from hypothesis import given

from .strategies import (
    SETTINGS,
    VERSION_POOL,
    pep440_versions,
    rich_specifier_sets,
)

if TYPE_CHECKING:
    from packaging.ranges import VersionRange
    from packaging.specifiers import SpecifierSet
    from packaging.version import Version

pytestmark = pytest.mark.property

# Cross-epoch + dev/MIN_VERSION boundary probes for the membership oracle.
_EPOCH_PROBES = [
    "0.5",
    "1.0",
    "1.0a1",
    "0.dev0",
    "1.dev0",
    "1.dev1",
    "1.dev2",
    "1!0.5",
    "1!1.0",
    "1!0.dev0",
    "2!0.5",
    "2!1.0",
    "3!1.0",
]


def _mem_eq(a: VersionRange, b: VersionRange) -> bool:
    """``a`` and ``b`` accept the same versions across the probe sample."""
    probes = [str(v) for v in VERSION_POOL] + _EPOCH_PROBES
    return all((p in a) == (p in b) for p in probes)


@given(a=rich_specifier_sets(), b=rich_specifier_sets())
@SETTINGS
def test_de_morgan_holds_cross_epoch(a: SpecifierSet, b: SpecifierSet) -> None:
    """De Morgan holds for ranges that may straddle different epochs.

    The minimal engine canonicalizes empty/MIN_VERSION regions, so the two
    sides can differ in bound representation; compare on the version set.
    """
    ra, rb = a.to_range(), b.to_range()
    assert _mem_eq((ra & rb).complement(), ra.complement() | rb.complement())
    assert _mem_eq((ra | rb).complement(), ra.complement() & rb.complement())


@given(
    a=rich_specifier_sets(),
    b=rich_specifier_sets(),
    v=pep440_versions(),
)
@SETTINGS
def test_membership_consistent_across_epochs(
    a: SpecifierSet, b: SpecifierSet, v: Version
) -> None:
    """``v in (a & b)`` iff ``v in a`` and ``v in b`` regardless of epochs."""
    ra, rb = a.to_range(), b.to_range()
    assert (v in (ra & rb)) == ((v in ra) and (v in rb))
    assert (v in (ra | rb)) == ((v in ra) or (v in rb))
