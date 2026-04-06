# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.

from __future__ import annotations

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

from packaging.specifiers import Specifier, SpecifierSet
from packaging.version import Version
from tests.property.strategies import (
    SETTINGS,
    local_labels,
    nonlocal_versions,
    pep440_versions,
    pre_tags,
    related_version_triple,
    release_versions,
    small_ints,
    specifier_sets,
)

pytestmark = pytest.mark.property


class TestFilterContainmentConsistency:
    """Implied by the definitions of filter() and contains(): filtering a list
    of versions should produce exactly the versions that individually satisfy
    the specifier."""

    @given(
        spec=specifier_sets(),
        versions=st.lists(pep440_versions(), min_size=0, max_size=15),
    )
    @SETTINGS
    def test_filter_equals_manual_containment(
        self, spec: SpecifierSet, versions: list[Version]
    ) -> None:
        """filter(vs) should equal [v for v in vs if v in spec]."""
        strs = [str(v) for v in versions]
        filtered = list(spec.filter(strs, prereleases=True))
        manual = [s for s in strs if spec.contains(s, prereleases=True)]
        assert filtered == manual

    @given(
        spec=specifier_sets(),
        versions=st.lists(pep440_versions(), min_size=0, max_size=15),
    )
    @SETTINGS
    def test_filter_preserves_order(
        self, spec: SpecifierSet, versions: list[Version]
    ) -> None:
        """filter() must return versions in the same order as the input."""
        strs = [str(v) for v in versions]
        filtered = list(spec.filter(strs, prereleases=True))
        # The filtered list must be a subsequence of the input.
        it = iter(strs)
        for f in filtered:
            for s in it:
                if s == f:
                    break
            else:
                raise AssertionError(f"{f} not found in remaining input")

    @given(
        spec=specifier_sets(),
        versions=st.lists(pep440_versions(), min_size=0, max_size=15),
    )
    @SETTINGS
    def test_filter_is_subset_of_input(
        self, spec: SpecifierSet, versions: list[Version]
    ) -> None:
        """Every version in filter output was in the input."""
        strs = [str(v) for v in versions]
        filtered = list(spec.filter(strs, prereleases=True))
        for v in filtered:
            assert v in strs


class TestSpecifierSetAndConsistency:
    """Implied by the definition of SpecifierSet.__and__: the & operator
    combines two specifier sets, and the result should match a version iff
    both operands match it."""

    @given(
        specifier_a=specifier_sets(),
        specifier_b=specifier_sets(),
        version=pep440_versions(),
    )
    @SETTINGS
    def test_and_matches_iff_both_match(
        self,
        specifier_a: SpecifierSet,
        specifier_b: SpecifierSet,
        version: Version,
    ) -> None:
        """(a & b).contains(v) iff a.contains(v) and b.contains(v)."""
        combined = specifier_a & specifier_b
        both = specifier_a.contains(version, prereleases=True) and specifier_b.contains(
            version, prereleases=True
        )
        assert combined.contains(version, prereleases=True) == both

    @given(
        specifier_a=specifier_sets(),
        specifier_b=specifier_sets(),
        version=pep440_versions(),
    )
    @SETTINGS
    def test_and_is_commutative(
        self,
        specifier_a: SpecifierSet,
        specifier_b: SpecifierSet,
        version: Version,
    ) -> None:
        """a & b and b & a accept the same versions."""
        ab = specifier_a & specifier_b
        b_and_a = specifier_b & specifier_a
        assert ab.contains(version, prereleases=True) == b_and_a.contains(
            version, prereleases=True
        )


class TestSpecifierRoundTrip:
    """Implied by the normalization rules: parsing a specifier and converting
    it back to a string should produce a stable, equivalent representation."""

    @given(version=nonlocal_versions())
    @SETTINGS
    def test_specifier_str_round_trip(self, version: Version) -> None:
        """Specifier(str(Specifier(s))) == Specifier(s)."""
        for op in [">=", "<=", ">", "<", "==", "!="]:
            s = f"{op}{version}"
            assert Specifier(str(Specifier(s))) == Specifier(s)

    @given(version=nonlocal_versions())
    @SETTINGS
    def test_specifier_set_str_round_trip(self, version: Version) -> None:
        """SpecifierSet(str(SpecifierSet(s))) == SpecifierSet(s)."""
        s = f">={version},<={version}"
        assert SpecifierSet(str(SpecifierSet(s))) == SpecifierSet(s)

    @given(spec=specifier_sets())
    @SETTINGS
    def test_specifier_set_str_round_trip_general(self, spec: SpecifierSet) -> None:
        """Any SpecifierSet round-trips through str."""
        assert SpecifierSet(str(spec)) == spec


class TestVersionPropertyConsistency:
    """Implied by the version scheme: the .public, .base_version, .major,
    .minor, .micro properties must be consistent with the parsed version
    components."""

    @given(version=pep440_versions())
    @SETTINGS
    def test_public_strips_local(self, version: Version) -> None:
        """Version(v.public) equals v with local removed."""
        pub = Version(version.public)
        assert pub == version.__replace__(local=None)

    @given(version=pep440_versions())
    @SETTINGS
    def test_base_version_strips_suffixes(self, version: Version) -> None:
        """Version(v.base_version) has no pre/post/dev/local."""
        base = Version(version.base_version)
        assert base.pre is None
        assert base.post is None
        assert base.dev is None
        assert base.local is None
        assert base.release == version.release
        assert base.epoch == version.epoch

    @given(version=pep440_versions())
    @SETTINGS
    def test_major_minor_micro_agree_with_release(self, version: Version) -> None:
        """major/minor/micro are the first three release components."""
        assert version.major == version.release[0]
        assert version.minor == (version.release[1] if len(version.release) > 1 else 0)
        assert version.micro == (version.release[2] if len(version.release) > 2 else 0)

    @given(version=pep440_versions())
    @SETTINGS
    def test_is_prerelease_iff_pre_or_dev(self, version: Version) -> None:
        """is_prerelease is True iff pre or dev is set."""
        assert version.is_prerelease == (
            version.pre is not None or version.dev is not None
        )

    @given(version=pep440_versions())
    @SETTINGS
    def test_is_postrelease_iff_post(self, version: Version) -> None:
        """is_postrelease is True iff post is set."""
        assert version.is_postrelease == (version.post is not None)

    @given(version=pep440_versions())
    @SETTINGS
    def test_is_devrelease_iff_dev(self, version: Version) -> None:
        """is_devrelease is True iff dev is set."""
        assert version.is_devrelease == (version.dev is not None)

    @given(version=pep440_versions())
    @SETTINGS
    def test_public_version_ordering(self, version: Version) -> None:
        """A version with local is >= its public version."""
        pub = Version(version.public)
        assert version >= pub


class TestMetamorphicVersionModifications:
    """Implied by the ordering rules: known modifications to a version
    should produce predictable ordering changes."""

    @given(version=release_versions())
    @SETTINGS
    def test_adding_post_increases(self, version: Version) -> None:
        """V.postN > V for any final release V."""
        post = Version(f"{version}.post0")
        assert post > version

    @given(version=release_versions())
    @SETTINGS
    def test_adding_dev_decreases(self, version: Version) -> None:
        """V.devN < V for any final release V."""
        dev = Version(f"{version}.dev0")
        assert dev < version

    @given(version=release_versions(), tag=pre_tags, number=small_ints)
    @SETTINGS
    def test_adding_pre_decreases(
        self, version: Version, tag: str, number: int
    ) -> None:
        """V.aN/bN/rcN < V for any final release V."""
        pre = Version(f"{version}{tag}{number}")
        assert pre < version

    @given(version=pep440_versions())
    @SETTINGS
    def test_bumping_last_segment_increases(self, version: Version) -> None:
        """Incrementing the last release segment produces a greater version."""
        release = list(version.release)
        release[-1] += 1
        bumped_str = ".".join(str(s) for s in release)
        if version.epoch:
            bumped_str = f"{version.epoch}!{bumped_str}"
        bumped = Version(bumped_str)
        assert bumped > version

    @given(
        version=pep440_versions(),
        higher_epoch=st.integers(min_value=1, max_value=5),
    )
    @SETTINGS
    def test_higher_epoch_always_wins(
        self, version: Version, higher_epoch: int
    ) -> None:
        """A version with a higher epoch is always greater."""
        epoch = version.epoch + higher_epoch
        other = Version(f"{epoch}!0")
        assert other > version

    @given(version=release_versions())
    @SETTINGS
    def test_appending_zero_segment_is_equal(self, version: Version) -> None:
        """V.0 == V due to zero-padding rules."""
        extended = Version(f"{version}.0")
        assert extended == version

    @given(
        version=nonlocal_versions(),
        local=local_labels,
    )
    @SETTINGS
    def test_adding_local_does_not_decrease(self, version: Version, local: str) -> None:
        """V+local >= V for any version."""
        with_local = Version(f"{version}+{local}")
        assert with_local >= version


class TestCompatibleReleaseBounds:
    """Implied by the compatible release definition: ~=V.N is equivalent
    to >=V.N, ==V.*, which means it has a clear lower and upper bound."""

    @given(version=release_versions(), candidate=pep440_versions())
    @SETTINGS
    def test_compatible_lower_bound(self, version: Version, candidate: Version) -> None:
        """If candidate matches ~=V then candidate >= V."""
        assume(candidate.local is None and len(version.release) >= 2)
        spec = Specifier(f"~={version}")
        if spec.contains(candidate, prereleases=True):
            assert candidate >= version

    @given(version=release_versions(), candidate=pep440_versions())
    @SETTINGS
    def test_compatible_upper_bound(self, version: Version, candidate: Version) -> None:
        """If candidate matches ~=V.N then candidate < (V_prefix+1).0."""
        assume(candidate.local is None and len(version.release) >= 2)
        spec = Specifier(f"~={version}")
        if spec.contains(candidate, prereleases=True):
            # Build the upper bound: bump the second-to-last segment.
            prefix = list(version.release[:-1])
            prefix[-1] += 1
            upper = Version(".".join(str(s) for s in prefix))
            if version.epoch:
                upper = Version(f"{version.epoch}!{upper}")
            assert candidate < upper

    @given(version=release_versions(), candidate=pep440_versions())
    @SETTINGS
    def test_compatible_matches_iff_expansion_matches(
        self, version: Version, candidate: Version
    ) -> None:
        """~=V.N matches iff >=V.N, ==V.* both match."""
        assume(candidate.local is None and len(version.release) >= 2)
        tilde = Specifier(f"~={version}")
        # Build the expansion: >=V, ==prefix.*
        prefix = ".".join(str(s) for s in version.release[:-1])
        if version.epoch:
            prefix = f"{version.epoch}!{prefix}"
        expanded = SpecifierSet(f">={version},=={prefix}.*")
        assert tilde.contains(candidate, prereleases=True) == expanded.contains(
            candidate, prereleases=True
        )


class TestTrichotomy:
    """Implied by the version ordering being a total order and the specifier
    definitions. The inclusive operators (>=, <=) have no exclusion rules
    and together with == form a true trichotomy. The exclusive operators
    (>, <) have pre/post/local exclusions so they are subsets of the
    inclusive operators."""

    @given(
        candidate=pep440_versions(),
        specifier_version=nonlocal_versions(),
    )
    @SETTINGS
    def test_inclusive_trichotomy(
        self, candidate: Version, specifier_version: Version
    ) -> None:
        """Exactly one of <=S (and not ==S), ==S, >=S (and not ==S) holds.

        Equivalently: >=S and <=S partition the version space into three
        disjoint groups (less, equal, greater) with ==S being the middle."""
        less_equal = Specifier(f"<={specifier_version}").contains(
            candidate, prereleases=True
        )
        equal = Specifier(f"=={specifier_version}").contains(
            candidate, prereleases=True
        )
        greater_equal = Specifier(f">={specifier_version}").contains(
            candidate, prereleases=True
        )
        # If equal, both inclusive ops match.
        if equal:
            assert less_equal
            assert greater_equal
        else:
            # Exactly one of <=S or >=S matches (not both, since == is
            # excluded, and at least one must hold by totality).
            assert less_equal != greater_equal, (
                f"candidate={candidate}, spec={specifier_version}: "
                f"<={less_equal}, =={equal}, >={greater_equal}"
            )

    @given(
        candidate=pep440_versions(),
        specifier_version=nonlocal_versions(),
    )
    @SETTINGS
    def test_greater_equal_equals_greater_than_or_equal(
        self, candidate: Version, specifier_version: Version
    ) -> None:
        """>=S matches iff >S or ==S matches.

        This may fail for pre/post/local-excluded versions (where >S
        rejects a version that is strictly greater in ordering). When
        it does, it reveals the exclusion gaps in > and <."""
        greater_equal = Specifier(f">={specifier_version}").contains(
            candidate, prereleases=True
        )
        greater_than = Specifier(f">{specifier_version}").contains(
            candidate, prereleases=True
        )
        equal = Specifier(f"=={specifier_version}").contains(
            candidate, prereleases=True
        )
        # >V is a subset of >=V, and ==V is a subset of >=V, so
        # (greater_than or equal) implies greater_equal. The reverse also
        # holds: >=V matches only if the candidate is either strictly greater
        # or equal, and the exclusions in >V only reduce its set.
        if greater_than or equal:
            assert greater_equal
        # The converse (greater_equal implies greater_than or equal) can fail
        # when >V excludes a post/pre/local of V. That gap is tested by the
        # cross-operator consistency tests elsewhere.

    @given(
        candidate=pep440_versions(),
        specifier_version=nonlocal_versions(),
    )
    @SETTINGS
    def test_less_equal_equals_less_than_or_equal(
        self, candidate: Version, specifier_version: Version
    ) -> None:
        """<=S matches iff <S or ==S matches (same caveat as above)."""
        less_equal = Specifier(f"<={specifier_version}").contains(
            candidate, prereleases=True
        )
        less_than = Specifier(f"<{specifier_version}").contains(
            candidate, prereleases=True
        )
        equal = Specifier(f"=={specifier_version}").contains(
            candidate, prereleases=True
        )
        if less_than or equal:
            assert less_equal


class TestZeroPaddingSpecifierInvariance:
    """Implied by the zero-padding rules: if V == V.0 as versions, then
    every specifier must treat them identically."""

    @given(version=release_versions(), candidate=pep440_versions())
    @SETTINGS
    def test_zero_padded_candidate_matches_same_specifiers(
        self, version: Version, candidate: Version
    ) -> None:
        """spec.contains(V) == spec.contains(V.0) for all specifiers."""
        padded = candidate.__replace__(release=(*candidate.release, 0))
        for op in [">=", "<=", ">", "<", "==", "!="]:
            spec = Specifier(f"{op}{version}")
            assert spec.contains(candidate, prereleases=True) == spec.contains(
                padded, prereleases=True
            ), f"{op}{version}: {candidate} and {padded} disagree"


class TestPrereleaseFlagOnlyAffectsPreReleases:
    """Implied by the pre-release handling rules: the prereleases flag
    should only affect versions that are actually pre-releases."""

    @given(spec=specifier_sets(), version=pep440_versions())
    @SETTINGS
    def test_non_prerelease_unaffected_by_flag(
        self, spec: SpecifierSet, version: Version
    ) -> None:
        """For non-prerelease versions, prereleases flag has no effect."""
        assume(not version.is_prerelease and version.local is None)
        assert spec.contains(version, prereleases=True) == spec.contains(
            version, prereleases=False
        )


class TestAndAgreesWithStringConcatenation:
    """Implied by SpecifierSet.__and__ semantics: the & operator should
    produce the same containment results as comma-joining the specifier
    strings."""

    @given(
        specifier_a=specifier_sets(),
        specifier_b=specifier_sets(),
        version=pep440_versions(),
    )
    @SETTINGS
    def test_and_equals_comma_join(
        self,
        specifier_a: SpecifierSet,
        specifier_b: SpecifierSet,
        version: Version,
    ) -> None:
        """(a & b).contains(v) == SpecifierSet(f"{a},{b}").contains(v)."""
        via_and = (specifier_a & specifier_b).contains(version, prereleases=True)
        joined = str(specifier_a) + ("," + str(specifier_b) if str(specifier_b) else "")
        via_str = SpecifierSet(joined).contains(version, prereleases=True)
        assert via_and == via_str


class TestLocalInvarianceForOrderingSpecifiers:
    """Implied by the spec: local version labels MUST be ignored entirely
    when checking if candidate versions match a given version specifier
    (except == with a local label)."""

    @given(
        version=nonlocal_versions(),
        specifier_version=nonlocal_versions(),
        local=local_labels,
    )
    @SETTINGS
    def test_local_ignored_for_all_ordering_ops(
        self, version: Version, specifier_version: Version, local: str
    ) -> None:
        """Adding local to a candidate doesn't change ordering specifier
        results."""
        with_local = Version(f"{version}+{local}")
        for op in [">=", "<=", ">", "<", "~="]:
            if op == "~=" and len(specifier_version.release) < 2:
                continue
            spec = Specifier(f"{op}{specifier_version}")
            assert spec.contains(version, prereleases=True) == spec.contains(
                with_local, prereleases=True
            ), f"{op}{specifier_version}: {version} and {with_local} disagree"


class TestComplementFilterPartition:
    """Implied by != being the exact complement of ==: filtering with
    == and != should partition the input list exactly."""

    @given(
        specifier_version=nonlocal_versions(),
        versions=st.lists(pep440_versions(), min_size=0, max_size=15),
    )
    @SETTINGS
    def test_equal_not_equal_partition_versions(
        self, specifier_version: Version, versions: list[Version]
    ) -> None:
        """filter(==V, vs) + filter(!=V, vs) == vs (as multisets)."""
        strs = [str(v) for v in versions if v.local is None]
        equal_spec = SpecifierSet(f"=={specifier_version}")
        not_equal_spec = SpecifierSet(f"!={specifier_version}")
        equal_filtered = list(equal_spec.filter(strs, prereleases=True))
        not_equal_filtered = list(not_equal_spec.filter(strs, prereleases=True))
        assert sorted(equal_filtered + not_equal_filtered) == sorted(strs)

    @given(
        specifier_version=release_versions(),
        versions=st.lists(pep440_versions(), min_size=0, max_size=15),
    )
    @SETTINGS
    def test_equal_not_equal_wildcard_partition_versions(
        self, specifier_version: Version, versions: list[Version]
    ) -> None:
        """filter(==V.*, vs) + filter(!=V.*, vs) == vs (as multisets)."""
        strs = [str(v) for v in versions if v.local is None]
        equal_spec = SpecifierSet(f"=={specifier_version}.*")
        not_equal_spec = SpecifierSet(f"!={specifier_version}.*")
        equal_filtered = list(equal_spec.filter(strs, prereleases=True))
        not_equal_filtered = list(not_equal_spec.filter(strs, prereleases=True))
        assert sorted(equal_filtered + not_equal_filtered) == sorted(strs)


class TestCrossOperatorConsistency:
    """Implied by the combination of the inclusive and exclusive ordered
    comparison sections, plus the version matching and exclusion sections.

    The six comparison operators (>=, <=, >, <, ==, !=) are defined
    independently but their semantics must be consistent with each other
    and with the version ordering."""

    @given(
        candidate=nonlocal_versions(),
        specifier_version=nonlocal_versions(),
    )
    @SETTINGS
    def test_greater_than_is_subset_of_greater_equal(
        self, candidate: Version, specifier_version: Version
    ) -> None:
        """If v matches >V then v must also match >=V."""
        greater_than = Specifier(f">{specifier_version}")
        greater_equal = Specifier(f">={specifier_version}")
        if greater_than.contains(candidate, prereleases=True):
            assert greater_equal.contains(candidate, prereleases=True), (
                f">{specifier_version} accepts {candidate} "
                f"but >={specifier_version} rejects it"
            )

    @given(
        candidate=nonlocal_versions(),
        specifier_version=nonlocal_versions(),
    )
    @SETTINGS
    def test_less_than_is_subset_of_less_equal(
        self, candidate: Version, specifier_version: Version
    ) -> None:
        """If v matches <V then v must also match <=V."""
        less_than = Specifier(f"<{specifier_version}")
        less_equal = Specifier(f"<={specifier_version}")
        if less_than.contains(candidate, prereleases=True):
            assert less_equal.contains(candidate, prereleases=True), (
                f"<{specifier_version} accepts {candidate} "
                f"but <={specifier_version} rejects it"
            )

    @given(
        candidate=nonlocal_versions(),
        specifier_version=nonlocal_versions(),
    )
    @SETTINGS
    def test_greater_than_and_less_than_are_disjoint(
        self, candidate: Version, specifier_version: Version
    ) -> None:
        """No version can match both >V and <V."""
        greater_than = Specifier(f">{specifier_version}")
        less_than = Specifier(f"<{specifier_version}")
        assert not (
            greater_than.contains(candidate, prereleases=True)
            and less_than.contains(candidate, prereleases=True)
        ), f"{candidate} matches both >{specifier_version} and <{specifier_version}"

    @given(
        candidate=nonlocal_versions(),
        specifier_version=nonlocal_versions(),
    )
    @SETTINGS
    def test_greater_equal_and_less_equal_intersection_implies_equal(
        self, candidate: Version, specifier_version: Version
    ) -> None:
        """If v matches both >=V and <=V then v must match ==V."""
        greater_equal = Specifier(f">={specifier_version}")
        less_equal = Specifier(f"<={specifier_version}")
        equal = Specifier(f"=={specifier_version}")
        if greater_equal.contains(candidate, prereleases=True) and less_equal.contains(
            candidate, prereleases=True
        ):
            assert equal.contains(candidate, prereleases=True), (
                f"{candidate} matches >={specifier_version} and "
                f"<={specifier_version} but not =={specifier_version}"
            )

    @given(
        candidate=nonlocal_versions(),
        specifier_version=nonlocal_versions(),
    )
    @SETTINGS
    def test_not_equal_accepts_everything_greater_than_accepts(
        self, candidate: Version, specifier_version: Version
    ) -> None:
        """If v matches >V then v must also match !=V."""
        greater_than = Specifier(f">{specifier_version}")
        not_equal = Specifier(f"!={specifier_version}")
        if greater_than.contains(candidate, prereleases=True):
            assert not_equal.contains(candidate, prereleases=True), (
                f">{specifier_version} accepts {candidate} "
                f"but !={specifier_version} rejects it"
            )

    @given(
        candidate=nonlocal_versions(),
        specifier_version=nonlocal_versions(),
    )
    @SETTINGS
    def test_not_equal_accepts_everything_less_than_accepts(
        self, candidate: Version, specifier_version: Version
    ) -> None:
        """If v matches <V then v must also match !=V."""
        less_than = Specifier(f"<{specifier_version}")
        not_equal = Specifier(f"!={specifier_version}")
        if less_than.contains(candidate, prereleases=True):
            assert not_equal.contains(candidate, prereleases=True), (
                f"<{specifier_version} accepts {candidate} "
                f"but !={specifier_version} rejects it"
            )

    @given(
        specifier_version=nonlocal_versions(),
        version_a=nonlocal_versions(),
        version_b=nonlocal_versions(),
    )
    @SETTINGS
    def test_greater_equal_monotonic(
        self, specifier_version: Version, version_a: Version, version_b: Version
    ) -> None:
        """If a matches >=V and b >= a, then b must also match >=V."""
        spec = Specifier(f">={specifier_version}")
        if spec.contains(version_a, prereleases=True) and version_b >= version_a:
            assert spec.contains(version_b, prereleases=True), (
                f">={specifier_version} accepts {version_a} but rejects "
                f"{version_b} even though {version_b} >= {version_a}"
            )

    @given(
        specifier_version=nonlocal_versions(),
        version_a=nonlocal_versions(),
        version_b=nonlocal_versions(),
    )
    @SETTINGS
    def test_less_equal_monotonic(
        self, specifier_version: Version, version_a: Version, version_b: Version
    ) -> None:
        """If a matches <=V and b <= a, then b must also match <=V."""
        spec = Specifier(f"<={specifier_version}")
        if spec.contains(version_a, prereleases=True) and version_b <= version_a:
            assert spec.contains(version_b, prereleases=True), (
                f"<={specifier_version} accepts {version_a} but rejects "
                f"{version_b} even though {version_b} <= {version_a}"
            )

    @given(
        candidate=nonlocal_versions(),
        specifier_version=nonlocal_versions(),
    )
    @SETTINGS
    def test_equal_wildcard_is_superset_of_equal(
        self, candidate: Version, specifier_version: Version
    ) -> None:
        """If v matches ==V then v must also match ==V.*."""
        # Wildcards are only valid on pure release segments.
        assume(
            not specifier_version.is_devrelease
            and not specifier_version.is_prerelease
            and not specifier_version.is_postrelease
        )
        equal = Specifier(f"=={specifier_version}")
        equal_wild = Specifier(f"=={specifier_version}.*")
        if equal.contains(candidate, prereleases=True):
            assert equal_wild.contains(candidate, prereleases=True), (
                f"=={specifier_version} accepts {candidate} "
                f"but =={specifier_version}.* rejects it"
            )

    @given(
        specifier_version=nonlocal_versions(),
        version_a=nonlocal_versions(),
        version_b=nonlocal_versions(),
    )
    @SETTINGS
    def test_greater_than_monotonic(
        self,
        specifier_version: Version,
        version_a: Version,
        version_b: Version,
    ) -> None:
        """If a matches >V and b > a, then b must also match >V."""
        spec = Specifier(f">{specifier_version}")
        if spec.contains(version_a, prereleases=True) and version_b > version_a:
            assert spec.contains(version_b, prereleases=True), (
                f">{specifier_version} accepts {version_a} "
                f"but rejects {version_b} even though "
                f"{version_b} > {version_a}"
            )

    @given(triple=related_version_triple())
    @SETTINGS
    def test_greater_than_monotonic_related(
        self, triple: tuple[Version, Version, Version]
    ) -> None:
        """If a matches >V and b > a, then b must also match >V.

        Same property as above but with versions sharing a release segment."""
        specifier_version, version_a, version_b = triple
        spec = Specifier(f">{specifier_version}")
        if spec.contains(version_a, prereleases=True) and version_b > version_a:
            assert spec.contains(version_b, prereleases=True), (
                f">{specifier_version} accepts {version_a} "
                f"but rejects {version_b} even though "
                f"{version_b} > {version_a}"
            )

    @given(
        specifier_version=nonlocal_versions(),
        version_a=nonlocal_versions(),
        version_b=nonlocal_versions(),
    )
    @SETTINGS
    def test_less_than_monotonic(
        self,
        specifier_version: Version,
        version_a: Version,
        version_b: Version,
    ) -> None:
        """If a matches <V and b < a, then b must also match <V."""
        spec = Specifier(f"<{specifier_version}")
        if spec.contains(version_a, prereleases=True) and version_b < version_a:
            assert spec.contains(version_b, prereleases=True), (
                f"<{specifier_version} accepts {version_a} "
                f"but rejects {version_b} even though "
                f"{version_b} < {version_a}"
            )

    @given(triple=related_version_triple())
    @SETTINGS
    def test_less_than_monotonic_related(
        self, triple: tuple[Version, Version, Version]
    ) -> None:
        """If a matches <V and b < a, then b must also match <V.

        Same property as above but with versions sharing a release segment."""
        specifier_version, version_a, version_b = triple
        spec = Specifier(f"<{specifier_version}")
        if spec.contains(version_a, prereleases=True) and version_b < version_a:
            assert spec.contains(version_b, prereleases=True), (
                f"<{specifier_version} accepts {version_a} "
                f"but rejects {version_b} even though "
                f"{version_b} < {version_a}"
            )
