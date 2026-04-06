# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.

from __future__ import annotations

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

from packaging.specifiers import InvalidSpecifier, Specifier, SpecifierSet
from packaging.version import Version
from tests.property.strategies import (
    SETTINGS,
    local_labels,
    nonlocal_versions,
    pre_tags,
    small_ints,
    specifier_sets,
    versions_with_local,
)

pytestmark = pytest.mark.property


class TestInclusiveOrderedComparison:
    """An inclusive ordered comparison clause includes a comparison operator and a
    version identifier, and will match any version where the comparison is correct
    based on the relative position of the candidate version and the specified
    version given the consistent ordering defined by the standard
    Version scheme.

    The inclusive ordered comparison operators are ``<=`` and ``>=``."""

    @given(
        candidate=nonlocal_versions(),
        specifier_version=nonlocal_versions(),
    )
    @SETTINGS
    def test_greater_equal_matches_iff_ordering_holds(
        self, candidate: Version, specifier_version: Version
    ) -> None:
        """>=V matches candidate iff candidate (public) >= V."""
        spec = Specifier(f">={specifier_version}")
        pub = Version(str(candidate).split("+")[0]) if candidate.local else candidate
        assert spec.contains(candidate, prereleases=True) == (pub >= specifier_version)

    @given(
        candidate=nonlocal_versions(),
        specifier_version=nonlocal_versions(),
    )
    @SETTINGS
    def test_less_equal_matches_iff_ordering_holds(
        self, candidate: Version, specifier_version: Version
    ) -> None:
        """<=V matches candidate iff candidate (public) <= V."""
        spec = Specifier(f"<={specifier_version}")
        pub = Version(str(candidate).split("+")[0]) if candidate.local else candidate
        assert spec.contains(candidate, prereleases=True) == (pub <= specifier_version)


class TestInclusiveOrderedComparisonZeroPadding:
    """As with version matching, the release segment is zero padded as necessary to
    ensure the release segments are compared with the same length."""

    @given(
        major=small_ints,
        minor=small_ints,
    )
    @SETTINGS
    def test_greater_equal_zero_padding(self, major: int, minor: int) -> None:
        """>=X.Y matches X.Y.0.0 because zero padding makes them equal."""
        spec = Specifier(f">={major}.{minor}")
        candidate = Version(f"{major}.{minor}.0.0")
        assert spec.contains(candidate, prereleases=True)

    @given(
        major=small_ints,
        minor=small_ints,
    )
    @SETTINGS
    def test_less_equal_zero_padding(self, major: int, minor: int) -> None:
        """<=X.Y matches X.Y.0.0 because zero padding makes them equal."""
        spec = Specifier(f"<={major}.{minor}")
        candidate = Version(f"{major}.{minor}.0.0")
        assert spec.contains(candidate, prereleases=True)

    @given(major=small_ints, minor=small_ints)
    @SETTINGS
    def test_greater_equal_padded_and_unpadded_are_equivalent(
        self, major: int, minor: int
    ) -> None:
        """>=X.Y and >=X.Y.0 should accept the same set of versions."""
        spec_short = Specifier(f">={major}.{minor}")
        spec_long = Specifier(f">={major}.{minor}.0")
        # They are semantically equivalent for any candidate.
        candidate = Version(f"{major}.{minor}")
        assert spec_short.contains(candidate, prereleases=True) == spec_long.contains(
            candidate, prereleases=True
        )


class TestInclusiveOrderedComparisonLocalVersions:
    """Local version identifiers are NOT permitted in this version specifier."""

    @given(specifier_version=versions_with_local())
    @SETTINGS
    def test_greater_equal_with_local_spec_raises(
        self, specifier_version: Version
    ) -> None:
        """Creating >= with a local version in the spec should raise."""
        with pytest.raises(InvalidSpecifier):
            Specifier(f">={specifier_version}")

    @given(specifier_version=versions_with_local())
    @SETTINGS
    def test_less_equal_with_local_spec_raises(
        self, specifier_version: Version
    ) -> None:
        """Creating <= with a local version in the spec should raise."""
        with pytest.raises(InvalidSpecifier):
            Specifier(f"<={specifier_version}")

    @given(
        candidate=versions_with_local(),
        specifier_version=nonlocal_versions(),
    )
    @SETTINGS
    def test_greater_equal_strips_local_from_candidate(
        self, candidate: Version, specifier_version: Version
    ) -> None:
        """>=V compares against the public version of the candidate."""
        spec = Specifier(f">={specifier_version}")
        pub = Version(str(candidate).split("+")[0])
        assert spec.contains(candidate, prereleases=True) == (pub >= specifier_version)

    @given(
        candidate=versions_with_local(),
        specifier_version=nonlocal_versions(),
    )
    @SETTINGS
    def test_less_equal_strips_local_from_candidate(
        self, candidate: Version, specifier_version: Version
    ) -> None:
        """<=V compares against the public version of the candidate."""
        spec = Specifier(f"<={specifier_version}")
        pub = Version(str(candidate).split("+")[0])
        assert spec.contains(candidate, prereleases=True) == (pub <= specifier_version)


class TestExclusiveOrderedComparisonDefinition:
    """The exclusive ordered comparisons ``>`` and ``<`` are similar to the inclusive
    ordered comparisons in that they rely on the relative position of the candidate
    version and the specified version given the consistent ordering defined by the
    standard Version scheme. However, they specifically exclude pre-releases,
    post-releases, and local versions of the specified version.

    Implied: ordered comparisons must be monotonic with respect to version
    ordering. If candidate ``a`` matches ``>V`` and ``b > a`` then ``b``
    must also match ``>V``. Symmetrically for ``<``."""

    @given(specifier_version=nonlocal_versions())
    @SETTINGS
    def test_greater_than_excludes_spec_version_itself(
        self, specifier_version: Version
    ) -> None:
        """>V does not match V."""
        spec = Specifier(f">{specifier_version}")
        assert not spec.contains(specifier_version, prereleases=True)

    @given(specifier_version=nonlocal_versions())
    @SETTINGS
    def test_less_than_excludes_spec_version_itself(
        self, specifier_version: Version
    ) -> None:
        """<V does not match V."""
        spec = Specifier(f"<{specifier_version}")
        assert not spec.contains(specifier_version, prereleases=True)

    @given(
        candidate=nonlocal_versions(),
        specifier_version=nonlocal_versions(),
    )
    @SETTINGS
    def test_greater_than_requires_candidate_strictly_greater(
        self, candidate: Version, specifier_version: Version
    ) -> None:
        """>V only matches candidates that are strictly greater than V."""
        spec = Specifier(f">{specifier_version}")
        if spec.contains(candidate, prereleases=True):
            assert candidate > specifier_version

    @given(
        candidate=nonlocal_versions(),
        specifier_version=nonlocal_versions(),
    )
    @SETTINGS
    def test_less_than_requires_candidate_strictly_less(
        self, candidate: Version, specifier_version: Version
    ) -> None:
        """<V only matches candidates that are strictly less than V."""
        spec = Specifier(f"<{specifier_version}")
        if spec.contains(candidate, prereleases=True):
            assert candidate < specifier_version


class TestExclusiveGtPostRelease:
    """The exclusive ordered comparison ``>V`` MUST NOT allow a post-release
    of the given version unless ``V`` itself is a post release. You may mandate
    that releases are later than a particular post release, including additional
    post releases, by using ``>V.postN``. For example, ``>1.7`` will allow
    ``1.7.1`` but not ``1.7.0.post1`` and ``>1.7.post2`` will allow ``1.7.1``
    and ``1.7.0.post3`` but not ``1.7.0``."""

    @given(
        specifier_version=nonlocal_versions(),
        post_num=st.integers(min_value=0, max_value=5),
    )
    @SETTINGS
    def test_greater_than_nonpost_excludes_post_of_itself(
        self, specifier_version: Version, post_num: int
    ) -> None:
        """>V (non-post) must not match V.postN."""
        assume(not specifier_version.is_postrelease)
        assume(not specifier_version.is_devrelease)
        postrelease_version = Version(f"{specifier_version}.post{post_num}")
        spec = Specifier(f">{specifier_version}")
        assert not spec.contains(postrelease_version, prereleases=True)

    def test_spec_example_gt_1_7(self) -> None:
        """>1.7 will allow 1.7.1 but not 1.7.0.post1."""
        spec = Specifier(">1.7")
        assert spec.contains("1.7.1", prereleases=True)
        assert not spec.contains("1.7.0.post1", prereleases=True)

    def test_spec_example_gt_1_7_post2(self) -> None:
        """>1.7.post2 will allow 1.7.1 and 1.7.0.post3 but not 1.7.0."""
        spec = Specifier(">1.7.post2")
        assert spec.contains("1.7.1", prereleases=True)
        assert spec.contains("1.7.0.post3", prereleases=True)
        assert not spec.contains("1.7.0", prereleases=True)

    @given(
        major=small_ints,
        minor=small_ints,
        pre=st.sampled_from([None, "a0", "b1", "rc1"]),
        post_n=st.integers(min_value=0, max_value=5),
        higher_post=st.integers(min_value=0, max_value=10),
    )
    @SETTINGS
    def test_greater_than_post_allows_higher_post(
        self,
        major: int,
        minor: int,
        pre: str | None,
        post_n: int,
        higher_post: int,
    ) -> None:
        """>V.postN allows V.postM where M > N."""
        assume(higher_post > post_n)
        base = f"{major}.{minor}{pre or ''}"
        spec = Specifier(f">{base}.post{post_n}")
        candidate = Version(f"{base}.post{higher_post}")
        assert spec.contains(candidate, prereleases=True)

    @given(
        specifier_version=nonlocal_versions(),
        bump=st.integers(min_value=1, max_value=5),
        post_num=st.integers(min_value=0, max_value=5),
    )
    @SETTINGS
    def test_greater_than_allows_post_of_later_release(
        self, specifier_version: Version, bump: int, post_num: int
    ) -> None:
        """>V allows (V+bump).postN since V+bump > V."""
        release = list(specifier_version.release)
        release[-1] += bump
        bumped = ".".join(str(s) for s in release)
        if specifier_version.epoch:
            bumped = f"{specifier_version.epoch}!{bumped}"
        candidate = Version(f"{bumped}.post{post_num}")
        spec = Specifier(f">{specifier_version}")
        assert spec.contains(candidate, prereleases=True)


class TestExclusiveGtLocalVersion:
    """The exclusive ordered comparison ``>V`` MUST NOT match a local version of
    the specified version."""

    @given(
        specifier_version=nonlocal_versions(),
        local_part=local_labels,
    )
    @SETTINGS
    def test_greater_than_excludes_local_of_spec_version(
        self, specifier_version: Version, local_part: str
    ) -> None:
        """>V must not match V+local."""
        local_ver = Version(f"{specifier_version}+{local_part}")
        spec = Specifier(f">{specifier_version}")
        assert not spec.contains(local_ver, prereleases=True)

    @given(
        specifier_version=nonlocal_versions(),
        bump=st.integers(min_value=1, max_value=5),
        local_part=local_labels,
    )
    @SETTINGS
    def test_greater_than_allows_local_of_later_version(
        self, specifier_version: Version, bump: int, local_part: str
    ) -> None:
        """>V allows (V+bump)+local since the public part is > V."""
        release = list(specifier_version.release)
        release[-1] += bump
        bumped = ".".join(str(s) for s in release)
        if specifier_version.epoch:
            bumped = f"{specifier_version.epoch}!{bumped}"
        candidate = Version(f"{bumped}+{local_part}")
        spec = Specifier(f">{specifier_version}")
        assert spec.contains(candidate, prereleases=True)


class TestExclusiveLtPreRelease:
    """The exclusive ordered comparison ``<V`` MUST NOT allow a pre-release of
    the specified version unless the specified version is itself a pre-release.
    Allowing pre-releases that are earlier than, but not equal to a specific
    pre-release may be accomplished by using ``<V.rc1`` or similar."""

    @given(
        specifier_version=nonlocal_versions(),
        pre_tag=pre_tags,
        pre_num=st.integers(min_value=0, max_value=5),
    )
    @SETTINGS
    def test_less_than_nonpre_excludes_pre_of_itself(
        self, specifier_version: Version, pre_tag: str, pre_num: int
    ) -> None:
        """<V (non-pre) must not match pre-releases of V."""
        assume(not specifier_version.is_prerelease)
        # Build a pre-release of specifier_version's base release segment.
        base = specifier_version.__replace__(pre=None, post=None, dev=None, local=None)
        prerelease_version = Version(f"{base}{pre_tag}{pre_num}")
        # Only test if the pre-release is actually a pre of specifier_version.
        earliest_pre = specifier_version.__replace__(dev=0, local=None)
        assume(prerelease_version >= earliest_pre)
        assume(prerelease_version < specifier_version)
        spec = Specifier(f"<{specifier_version}")
        assert not spec.contains(prerelease_version, prereleases=True)

    @given(
        specifier_version=nonlocal_versions(),
        earlier_pre_tag=pre_tags,
        earlier_pre_num=st.integers(min_value=0, max_value=5),
    )
    @SETTINGS
    def test_less_than_prerelease_allows_earlier_prerelease(
        self,
        specifier_version: Version,
        earlier_pre_tag: str,
        earlier_pre_num: int,
    ) -> None:
        """<V.rc1 (or similar) allows earlier pre-releases."""
        assume(specifier_version.is_prerelease)
        base = specifier_version.__replace__(pre=None, post=None, dev=None, local=None)
        candidate = Version(f"{base}{earlier_pre_tag}{earlier_pre_num}")
        assume(candidate < specifier_version)
        spec = Specifier(f"<{specifier_version}")
        assert spec.contains(candidate, prereleases=True)

    @given(
        specifier_version=nonlocal_versions(),
        decrement=st.integers(min_value=1, max_value=5),
        pre_tag=pre_tags,
        pre_num=st.integers(min_value=0, max_value=5),
    )
    @SETTINGS
    def test_less_than_allows_pre_of_earlier_release(
        self, specifier_version: Version, decrement: int, pre_tag: str, pre_num: int
    ) -> None:
        """<V allows pre-releases of a strictly earlier release."""
        release = list(specifier_version.release)
        assume(release[-1] >= decrement)
        release[-1] -= decrement
        earlier = ".".join(str(s) for s in release)
        if specifier_version.epoch:
            earlier = f"{specifier_version.epoch}!{earlier}"
        candidate = Version(f"{earlier}{pre_tag}{pre_num}")
        spec = Specifier(f"<{specifier_version}")
        assert spec.contains(candidate, prereleases=True)

    def test_spec_example_lt_with_prerelease_spec(self) -> None:
        """<1.0rc1 allows 1.0a1 and 1.0b2 but not 1.0rc1 itself."""
        spec = Specifier("<1.0rc1")
        assert spec.contains("1.0a1", prereleases=True)
        assert spec.contains("1.0b2", prereleases=True)
        assert not spec.contains("1.0rc1", prereleases=True)

    def test_less_than_final_excludes_dev_of_same_base(self) -> None:
        """<1.0 should not match 1.0.dev0 (dev releases are pre-releases)."""
        spec = Specifier("<1.0")
        assert not spec.contains("1.0.dev0", prereleases=True)


class TestExclusiveOrderedComparisonZeroPadding:
    """As with version matching, the release segment is zero padded as necessary to
    ensure the release segments are compared with the same length."""

    @given(major=small_ints, minor=small_ints)
    @SETTINGS
    def test_greater_than_zero_padded_equivalence(self, major: int, minor: int) -> None:
        """>X.Y and >X.Y.0 are semantically equivalent."""
        spec_short = Specifier(f">{major}.{minor}")
        spec_long = Specifier(f">{major}.{minor}.0")
        # They should agree on a version that is clearly higher.
        high = Version(f"{major}.{minor + 1}")
        assert spec_short.contains(high, prereleases=True) == spec_long.contains(
            high, prereleases=True
        )

    @given(major=small_ints, minor=small_ints)
    @SETTINGS
    def test_less_than_zero_padded_equivalence(self, major: int, minor: int) -> None:
        """<X.Y and <X.Y.0 are semantically equivalent."""
        assume(major > 0 or minor > 0)
        spec_short = Specifier(f"<{major}.{minor}")
        spec_long = Specifier(f"<{major}.{minor}.0")
        # They should agree on a version that is clearly lower.
        low = Version("0.0.1") if major > 0 or minor > 1 else Version("0.0")
        assert spec_short.contains(low, prereleases=True) == spec_long.contains(
            low, prereleases=True
        )


class TestExclusiveOrderedComparisonLocalVersions:
    """Local version identifiers are NOT permitted in this version specifier."""

    @given(specifier_version=versions_with_local())
    @SETTINGS
    def test_greater_than_with_local_spec_raises(
        self, specifier_version: Version
    ) -> None:
        """Creating > with a local version in the spec should raise."""
        with pytest.raises(InvalidSpecifier):
            Specifier(f">{specifier_version}")

    @given(specifier_version=versions_with_local())
    @SETTINGS
    def test_less_than_with_local_spec_raises(self, specifier_version: Version) -> None:
        """Creating < with a local version in the spec should raise."""
        with pytest.raises(InvalidSpecifier):
            Specifier(f"<{specifier_version}")


class TestArbitraryEqualityDefinition:
    """Arbitrary equality comparisons are simple string equality operations which do
    not take into account any of the semantic information such as zero padding or
    local versions. The comparison MUST treat ASCII letters case-insensitively, e.g.
    by lowercasing, and is unspecified for non-ASCII text. This operator also does
    not support prefix matching as the ``==`` operator does.

    The primary use case for arbitrary equality is to allow for specifying
    a version which cannot otherwise be represented by this specification.
    This operator is special and acts as an escape hatch to allow someone
    using a tool which implements this specification to still install a
    legacy version which is otherwise incompatible with this
    specification."""

    @given(
        ver_str=st.sampled_from(
            ["1.0", "2.0.1", "foobar", "1.0a1", "1.0.post1", "1.0+local"]
        )
    )
    @SETTINGS
    def test_arbitrary_matches_exact_string(self, ver_str: str) -> None:
        """===X matches the string X."""
        spec = Specifier(f"==={ver_str}")
        assert spec.contains(ver_str, prereleases=True)

    @given(ver_str=st.sampled_from(["FooBar", "HELLO", "AbC.1", "Version1"]))
    @SETTINGS
    def test_arbitrary_case_insensitive(self, ver_str: str) -> None:
        """=== comparison is case-insensitive for ASCII."""
        spec = Specifier(f"==={ver_str}")
        assert spec.contains(ver_str.lower(), prereleases=True)
        assert spec.contains(ver_str.upper(), prereleases=True)

    @given(major=small_ints, minor=small_ints)
    @SETTINGS
    def test_arbitrary_no_zero_padding(self, major: int, minor: int) -> None:
        """===X.Y does NOT match X.Y.0 (no zero padding semantics)."""
        spec = Specifier(f"==={major}.{minor}")
        padded = f"{major}.{minor}.0"
        # Only matches if the strings are literally equal (they are not).
        assert not spec.contains(padded, prereleases=True)

    @given(
        base=st.sampled_from(["1.0", "2.3", "0.1"]),
        suffix=st.sampled_from(["1", ".0", ".1", "a"]),
    )
    @SETTINGS
    def test_arbitrary_no_prefix_matching(self, base: str, suffix: str) -> None:
        """=== does not support prefix matching like == does."""
        spec = Specifier(f"==={base}")
        extended = f"{base}{suffix}"
        assume(extended.lower() != base.lower())
        assert not spec.contains(extended, prereleases=True)


class TestArbitraryEqualityFoobar:
    """An example would be ``===foobar`` which would match a version of ``foobar``."""

    def test_foobar_example(self) -> None:
        """===foobar matches foobar."""
        spec = Specifier("===foobar")
        assert spec.contains("foobar", prereleases=True)

    def test_foobar_case_insensitive(self) -> None:
        """===foobar matches FOOBAR (case-insensitive)."""
        spec = Specifier("===foobar")
        assert spec.contains("FOOBAR", prereleases=True)

    def test_foobar_does_not_match_other(self) -> None:
        """===foobar does not match barbaz."""
        spec = Specifier("===foobar")
        assert not spec.contains("barbaz", prereleases=True)


class TestArbitraryEqualityNoLocal:
    """This operator may also be used to explicitly require an unpatched version
    of a project such as ``===1.0`` which would not match for a version
    ``1.0+downstream1``."""

    def test_spec_example_1_0_no_downstream(self) -> None:
        """===1.0 does not match 1.0+downstream1."""
        spec = Specifier("===1.0")
        assert not spec.contains("1.0+downstream1", prereleases=True)

    @given(
        ver_str=st.sampled_from(["1.0", "2.0", "3.1.4"]),
        local=st.sampled_from(["downstream1", "ubuntu1", "local.1"]),
    )
    @SETTINGS
    def test_arbitrary_excludes_local_variants(self, ver_str: str, local: str) -> None:
        """===V does not match V+local."""
        spec = Specifier(f"==={ver_str}")
        assert not spec.contains(f"{ver_str}+{local}", prereleases=True)

    @given(ver_str=st.sampled_from(["1.0", "2.0", "3.1.4"]))
    @SETTINGS
    def test_arbitrary_matches_exact(self, ver_str: str) -> None:
        """===V does match V exactly."""
        spec = Specifier(f"==={ver_str}")
        assert spec.contains(ver_str, prereleases=True)


class TestPreReleaseImplicitExclusion:
    """Pre-releases of any kind, including developmental releases, are implicitly
    excluded from all version specifiers, unless they are already present
    on the system, explicitly requested by the user, or if the only available
    version that satisfies the version specifier is a pre-release.

    By default, dependency resolution tools SHOULD:

    * accept already installed pre-releases for all version specifiers
    * accept remotely available pre-releases for version specifiers where
      there is no final or post release that satisfies the version specifier
    * exclude all other pre-releases from consideration

    Dependency resolution tools SHOULD also allow users to request the
    following alternative behaviours:

    * accepting pre-releases for all version specifiers
    * excluding pre-releases for all version specifiers"""

    @given(
        major=st.integers(min_value=0, max_value=10),
        minor=st.integers(min_value=0, max_value=10),
        bump=st.integers(min_value=1, max_value=5),
        pre_tag=pre_tags,
        pre_num=st.integers(min_value=0, max_value=5),
    )
    @SETTINGS
    def test_pre_excluded_by_default_when_finals_exist(
        self, major: int, minor: int, bump: int, pre_tag: str, pre_num: int
    ) -> None:
        """A pre-release is excluded when a final release also matches."""
        specifier_version = Version(f"{major}.{minor}")
        # Create a pre-release of a *later* version so it satisfies >=specifier_version.
        later = Version(f"{major}.{minor + bump}")
        prerelease_version = Version(f"{major}.{minor + bump}{pre_tag}{pre_num}")
        spec = Specifier(f">={specifier_version}")
        # With both a final and pre-release available, default filtering
        # should exclude the pre-release.
        candidates = [str(later), str(prerelease_version)]
        filtered = list(spec.filter(candidates))
        assert str(later) in filtered
        assert str(prerelease_version) not in filtered

    @given(
        major=st.integers(min_value=0, max_value=10),
        minor=st.integers(min_value=0, max_value=10),
        bump=st.integers(min_value=1, max_value=5),
        pre_tag=pre_tags,
        pre_num=st.integers(min_value=0, max_value=5),
    )
    @SETTINGS
    def test_pre_included_when_explicitly_requested(
        self, major: int, minor: int, bump: int, pre_tag: str, pre_num: int
    ) -> None:
        """Pre-releases are included when prereleases=True."""
        specifier_version = Version(f"{major}.{minor}")
        prerelease_version = Version(f"{major}.{minor + bump}{pre_tag}{pre_num}")
        spec = Specifier(f">={specifier_version}")
        filtered = list(
            spec.filter(
                [str(specifier_version), str(prerelease_version)], prereleases=True
            )
        )
        assert str(prerelease_version) in filtered

    @given(
        major=st.integers(min_value=0, max_value=10),
        minor=st.integers(min_value=0, max_value=10),
        bump=st.integers(min_value=1, max_value=5),
        pre_tag=pre_tags,
        pre_num=st.integers(min_value=0, max_value=5),
    )
    @SETTINGS
    def test_pre_included_when_only_available(
        self, major: int, minor: int, bump: int, pre_tag: str, pre_num: int
    ) -> None:
        """Pre-releases are included if they are the only matching version."""
        specifier_version = Version(f"{major}.{minor}")
        prerelease_version = Version(f"{major}.{minor + bump}{pre_tag}{pre_num}")
        spec = Specifier(f">={specifier_version}")
        # Only the pre-release is available.
        filtered = list(spec.filter([str(prerelease_version)]))
        assert str(prerelease_version) in filtered

    @given(
        major=st.integers(min_value=0, max_value=10),
        minor=st.integers(min_value=0, max_value=10),
        bump=st.integers(min_value=1, max_value=5),
        pre_tag=pre_tags,
        pre_num=st.integers(min_value=0, max_value=5),
    )
    @SETTINGS
    def test_pre_excluded_when_explicitly_disabled(
        self, major: int, minor: int, bump: int, pre_tag: str, pre_num: int
    ) -> None:
        """Pre-releases are excluded when prereleases=False."""
        specifier_version = Version(f"{major}.{minor}")
        prerelease_version = Version(f"{major}.{minor + bump}{pre_tag}{pre_num}")
        spec = Specifier(f">={specifier_version}")
        filtered = list(
            spec.filter(
                [str(specifier_version), str(prerelease_version)], prereleases=False
            )
        )
        assert str(prerelease_version) not in filtered

    @given(version=nonlocal_versions())
    @SETTINGS
    def test_dev_release_is_also_prerelease(self, version: Version) -> None:
        """Dev releases are pre-releases and subject to the same exclusion."""
        assume(version.is_devrelease)
        assert version.is_prerelease

    @given(
        major=st.integers(min_value=0, max_value=10),
        minor=st.integers(min_value=0, max_value=10),
        bump=st.integers(min_value=1, max_value=5),
        pre_tag=pre_tags,
        pre_num=st.integers(min_value=0, max_value=5),
    )
    @SETTINGS
    def test_specifier_set_pre_fallback_when_no_finals(
        self, major: int, minor: int, bump: int, pre_tag: str, pre_num: int
    ) -> None:
        """SpecifierSet.filter with default prereleases returns
        pre-releases when no final release satisfies the specifier."""
        spec = SpecifierSet(f">={major}.{minor}")
        prerelease_version = Version(f"{major}.{minor + bump}{pre_tag}{pre_num}")
        filtered = list(spec.filter([str(prerelease_version)]))
        assert str(prerelease_version) in filtered

    @given(
        major=st.integers(min_value=0, max_value=10),
        minor=st.integers(min_value=0, max_value=10),
        bump=st.integers(min_value=1, max_value=5),
        pre_tag=pre_tags,
        pre_num=st.integers(min_value=0, max_value=5),
    )
    @SETTINGS
    def test_specifier_set_pre_excluded_by_default(
        self, major: int, minor: int, bump: int, pre_tag: str, pre_num: int
    ) -> None:
        """SpecifierSet.filter with default prereleases excludes
        pre-releases when a final release is also available."""
        later = Version(f"{major}.{minor + bump}")
        prerelease_version = Version(f"{major}.{minor + bump}{pre_tag}{pre_num}")
        spec = SpecifierSet(f">={major}.{minor}")
        filtered = list(spec.filter([str(later), str(prerelease_version)]))
        assert str(later) in filtered
        assert str(prerelease_version) not in filtered

    @given(
        spec=specifier_sets(),
        versions=st.lists(nonlocal_versions(), max_size=15),
    )
    @SETTINGS
    def test_prereleases_false_never_yields_prerelease(
        self, spec: SpecifierSet, versions: list[Version]
    ) -> None:
        """filter(vs, prereleases=False) never returns a pre-release."""
        strs = [str(version) for version in versions]
        filtered = list(spec.filter(strs, prereleases=False))
        for version_str in filtered:
            assert not Version(version_str).is_prerelease


class TestPostAndFinalReleasesAlwaysIncluded:
    """Post-releases and final releases receive no special treatment in version
    specifiers - they are always included unless explicitly excluded."""

    @given(version=nonlocal_versions())
    @SETTINGS
    def test_post_release_not_excluded_by_default(self, version: Version) -> None:
        """Post-releases are included in default filtering."""
        assume(version.is_postrelease and version.local is None)
        spec = Specifier(f">={version}")
        filtered = list(spec.filter([str(version)]))
        assert str(version) in filtered

    @given(version=nonlocal_versions())
    @SETTINGS
    def test_final_release_not_excluded_by_default(self, version: Version) -> None:
        """Final releases are included in default filtering."""
        assume(not version.is_prerelease and not version.is_postrelease)
        assume(not version.is_devrelease and version.local is None)
        spec = Specifier(f">={version}")
        filtered = list(spec.filter([str(version)]))
        assert str(version) in filtered

    @given(
        major=st.integers(min_value=0, max_value=10),
        minor=st.integers(min_value=0, max_value=10),
        bump=st.integers(min_value=1, max_value=5),
        post_num=st.integers(min_value=0, max_value=5),
        pre_tag=pre_tags,
        pre_num=st.integers(min_value=0, max_value=5),
    )
    @SETTINGS
    def test_post_included_while_pre_excluded(
        self,
        major: int,
        minor: int,
        bump: int,
        post_num: int,
        pre_tag: str,
        pre_num: int,
    ) -> None:
        """When both post and pre are available, post is included, pre is not."""
        base = Version(f"{major}.{minor}")
        # Post-release of the base version is always >= base.
        postrelease_version = Version(f"{base}.post{post_num}")
        # Pre-release of a later version so it satisfies >=base.
        prerelease_version = Version(f"{major}.{minor + bump}{pre_tag}{pre_num}")
        spec = Specifier(f">={base}")
        filtered = list(
            spec.filter([str(base), str(postrelease_version), str(prerelease_version)])
        )
        assert str(postrelease_version) in filtered
        assert str(base) in filtered
        assert str(prerelease_version) not in filtered
