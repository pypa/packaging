# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.

from __future__ import annotations

import typing

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

from packaging.specifiers import SpecifierSet
from tests.property.strategies import (
    SETTINGS,
    VERSION_POOL,
    nonlocal_versions,
    pep440_versions,
    release_versions,
    specifier_sets,
)

if typing.TYPE_CHECKING:
    from packaging.version import Version

pytestmark = pytest.mark.property


@st.composite
def unsatisfiable_sets(draw: st.DrawFn) -> SpecifierSet:
    """Build a SpecifierSet that is guaranteed unsatisfiable."""
    pattern = draw(
        st.sampled_from(
            [
                "contradictory_range",
                "equal_not_equal",
                "equal_not_equal_wildcard",
                "contradictory_pins",
            ]
        )
    )

    if pattern == "contradictory_range":
        lo = draw(nonlocal_versions())
        hi = draw(nonlocal_versions())
        assume(hi > lo)
        return SpecifierSet(f">={hi},<{lo}")

    if pattern == "equal_not_equal":
        v = draw(pep440_versions())
        return SpecifierSet(f"=={v},!={v}")

    if pattern == "equal_not_equal_wildcard":
        v = draw(release_versions())
        return SpecifierSet(f"=={v}.*,!={v}.*")

    # contradictory_pins: ==X,==Y where X != Y
    # Local versions excluded: ==V (no local) matches V+local, so
    # ==1.0 and ==1.0+local are not contradictory.
    a = draw(nonlocal_versions())
    b = draw(nonlocal_versions())
    assume(a != b)
    return SpecifierSet(f"=={a},=={b}")


class TestIsUnsatisfiableSoundness:
    """Logical properties of is_unsatisfiable() that follow from its
    definition but are not stated in PEP 440."""

    @given(spec=unsatisfiable_sets(), version=pep440_versions())
    @SETTINGS
    def test_unsatisfiable_rejects_all_versions(
        self, spec: SpecifierSet, version: Version
    ) -> None:
        """An unsatisfiable set must reject every version."""
        assert spec.is_unsatisfiable()
        assert not spec.contains(version, prereleases=True)

    @given(spec=specifier_sets())
    @SETTINGS
    def test_filter_nonempty_implies_satisfiable(self, spec: SpecifierSet) -> None:
        """If filter finds any match in VERSION_POOL, the set is satisfiable."""
        versions = [str(v) for v in VERSION_POOL]
        if list(spec.filter(versions, prereleases=True)):
            assert not spec.is_unsatisfiable()

    @given(spec_a=unsatisfiable_sets(), spec_b=specifier_sets())
    @SETTINGS
    def test_unsatisfiable_monotone_under_intersection(
        self, spec_a: SpecifierSet, spec_b: SpecifierSet
    ) -> None:
        """Adding constraints to an unsatisfiable set keeps it unsatisfiable."""
        assert (spec_a & spec_b).is_unsatisfiable()

    @given(
        spec_a=specifier_sets(),
        spec_b=specifier_sets(),
        version=pep440_versions(),
    )
    @SETTINGS
    def test_and_agrees_with_is_unsatisfiable(
        self,
        spec_a: SpecifierSet,
        spec_b: SpecifierSet,
        version: Version,
    ) -> None:
        """If A & B is satisfiable, any version it accepts must be
        accepted by both A and B individually."""
        combined = spec_a & spec_b
        if combined.contains(version, prereleases=True):
            assert not combined.is_unsatisfiable()
            assert spec_a.contains(version, prereleases=True)
            assert spec_b.contains(version, prereleases=True)


class TestIsUnsatisfiableWithPrereleases:
    """Logical properties of is_unsatisfiable() when prereleases=False.
    A set whose only solutions are pre-releases should be reported as
    unsatisfiable."""

    @given(spec=specifier_sets())
    @SETTINGS
    def test_prereleases_false_unsatisfiable_implies_empty_filter(
        self, spec: SpecifierSet
    ) -> None:
        """If unsatisfiable with prereleases=False, filter returns nothing."""
        ss = SpecifierSet(str(spec), prereleases=False)
        if ss.is_unsatisfiable():
            versions = [str(v) for v in VERSION_POOL]
            assert not list(ss.filter(versions))

    @given(
        spec=specifier_sets(),
        version=nonlocal_versions(),
    )
    @SETTINGS
    def test_prereleases_false_unsatisfiable_rejects_non_prereleases(
        self, spec: SpecifierSet, version: Version
    ) -> None:
        """If unsatisfiable with prereleases=False, non-prerelease
        versions cannot match."""
        ss = SpecifierSet(str(spec), prereleases=False)
        if ss.is_unsatisfiable() and not version.is_prerelease:
            assert not ss.contains(version)
