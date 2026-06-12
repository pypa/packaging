# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.

"""Property tests for ``VersionRange`` algebra across distinct epochs.

PEP 440 epochs partition the version order into disjoint cohorts; an
``==1.0`` predicate in epoch 0 never overlaps an ``==1.0`` predicate in
epoch 1. The lattice laws still hold across cohorts, and round-tripping
through :meth:`to_specifier_set` must preserve the epoch on every side.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from hypothesis import given

from .strategies import (
    SETTINGS,
    pep440_versions,
    rich_specifier_sets,
)

if TYPE_CHECKING:
    from packaging.specifiers import SpecifierSet
    from packaging.version import Version

pytestmark = pytest.mark.property


@given(a=rich_specifier_sets(), b=rich_specifier_sets())
@SETTINGS
def test_de_morgan_holds_cross_epoch(a: SpecifierSet, b: SpecifierSet) -> None:
    """De Morgan holds for ranges that may straddle different epochs."""
    ra, rb = a.to_range(), b.to_range()
    assert (ra & rb).complement() == ra.complement() | rb.complement()
    assert (ra | rb).complement() == ra.complement() & rb.complement()


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


@given(spec_set=rich_specifier_sets())
@SETTINGS
def test_single_set_round_trip_preserves_epoch(spec_set: SpecifierSet) -> None:
    """``to_specifier_set`` round-trips epochs when the single-set form exists.

    When the conversion returns a single set, feeding it back through
    ``from_specifier_set`` must accept exactly the same versions; in
    particular any cross-epoch boundary in the source survives.
    """
    r = spec_set.to_range()
    converted = r.to_specifier_set()
    if converted is None:
        return
    recovered = converted.to_range()
    # Membership on a cross-epoch probe set must round-trip.
    probes = [
        "0.5",
        "1.0",
        "1.0a1",
        "1!0.5",
        "1!1.0",
        "2!0.5",
        "2!1.0",
        "3!1.0",
    ]
    for probe in probes:
        assert (probe in r) == (probe in recovered)
