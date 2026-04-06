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
    multi_segment_versions,
    nonlocal_versions,
    ops,
    pep440_versions,
    release_versions,
    small_ints,
    versions_with_local,
)

pytestmark = pytest.mark.property


class TestSpecifierCommaIsAnd:
    """The comma (",") is equivalent to a logical **and** operator: a candidate
    version must match all given version clauses in order to match the
    specifier as a whole."""

    @given(version=release_versions())
    @SETTINGS
    def test_comma_separated_is_conjunction(self, version: Version) -> None:
        """A version matches a multi-clause specifier iff it matches every clause."""
        clauses = [f">={version}", f"<={version}"]
        combined = SpecifierSet(",".join(clauses))
        individual = [SpecifierSet(c) for c in clauses]
        matches_all = all(version in s for s in individual)
        assert (version in combined) == matches_all

    @given(candidate=pep440_versions(), data=st.data())
    @SETTINGS
    def test_adding_clause_can_only_narrow(
        self, candidate: Version, data: st.DataObject
    ) -> None:
        """Adding a clause to a specifier set can never cause a previously
        excluded version to start matching."""
        base_op = data.draw(ops)
        base_ver = data.draw(release_versions())
        extra_op = data.draw(ops)
        extra_ver = data.draw(release_versions())

        base_spec = SpecifierSet(f"{base_op}{base_ver}")
        combined = SpecifierSet(f"{base_op}{base_ver},{extra_op}{extra_ver}")
        if candidate in combined:
            assert candidate in base_spec

    @given(
        first_op=ops,
        first_ver=release_versions(),
        second_op=ops,
        second_ver=release_versions(),
        candidate=pep440_versions(),
    )
    @SETTINGS
    def test_intersection_is_idempotent(
        self,
        first_op: str,
        first_ver: Version,
        second_op: str,
        second_ver: Version,
        candidate: Version,
    ) -> None:
        """(A & B) & B accepts the same versions as A & B."""
        combined = SpecifierSet(f"{first_op}{first_ver},{second_op}{second_ver}")
        combined_double = SpecifierSet(
            f"{first_op}{first_ver},{second_op}{second_ver},{second_op}{second_ver}"
        )
        assert combined.contains(
            candidate, prereleases=True
        ) == combined_double.contains(candidate, prereleases=True)

    @given(
        first_op=ops,
        first_ver=release_versions(),
        second_op=ops,
        second_ver=release_versions(),
        third_op=ops,
        third_ver=release_versions(),
        candidate=pep440_versions(),
    )
    @SETTINGS
    def test_intersection_is_associative(
        self,
        first_op: str,
        first_ver: Version,
        second_op: str,
        second_ver: Version,
        third_op: str,
        third_ver: Version,
        candidate: Version,
    ) -> None:
        """(A & B) & C accepts the same versions as A & (B & C)."""
        combined = SpecifierSet(
            f"{first_op}{first_ver},{second_op}{second_ver},{third_op}{third_ver}"
        )
        # Since comma is AND regardless of grouping, any ordering
        # of the same clauses must agree on containment.
        assert (candidate in combined) == (
            SpecifierSet(f"{first_op}{first_ver}").contains(candidate, prereleases=True)
            and SpecifierSet(f"{second_op}{second_ver}").contains(
                candidate, prereleases=True
            )
            and SpecifierSet(f"{third_op}{third_ver}").contains(
                candidate, prereleases=True
            )
        )


class TestSpecifierWhitespace:
    """Whitespace between a conditional operator and the following version
    identifier is optional, as is the whitespace around the commas."""

    @given(spec_ver=release_versions(), spaces=st.integers(min_value=0, max_value=3))
    @SETTINGS
    def test_whitespace_between_op_and_version(
        self, spec_ver: Version, spaces: int
    ) -> None:
        """Whitespace between operator and version doesn't change semantics."""
        ws = " " * spaces
        spec_no_ws = Specifier(f"=={spec_ver}")
        spec_ws = Specifier(f"=={ws}{spec_ver}")
        assert spec_no_ws == spec_ws

    @given(
        v1=release_versions(),
        v2=release_versions(),
        spaces=st.integers(min_value=0, max_value=3),
    )
    @SETTINGS
    def test_whitespace_around_commas(
        self, v1: Version, v2: Version, spaces: int
    ) -> None:
        """Whitespace around commas doesn't change semantics."""
        ws = " " * spaces
        spec_no_ws = SpecifierSet(f">={v1},<={v2}")
        spec_ws = SpecifierSet(f">={v1}{ws},{ws}<={v2}")
        assert spec_no_ws == spec_ws


class TestLocalVersionIgnoredInSpecifiers:
    """Except where specifically noted below, local version identifiers MUST NOT be
    permitted in version specifiers, and local version labels MUST be ignored
    entirely when checking if candidate versions match a given version
    specifier."""

    @given(version=versions_with_local())
    @SETTINGS
    def test_local_ignored_for_ordering_specifiers(self, version: Version) -> None:
        """A version with a local label matches >= and <= on its public version."""
        public = Version(str(version).split("+")[0])
        spec = SpecifierSet(f">={public}")
        assert version in spec

    @given(version=versions_with_local())
    @SETTINGS
    def test_local_ignored_for_gt(self, version: Version) -> None:
        """Local labels are stripped before comparison for > specifiers."""
        public = Version(str(version).split("+")[0])
        # version's local is ignored, so it compares as public; public is not > public
        spec = Specifier(f">{public}")
        assert version not in spec

    @given(version=versions_with_local())
    @SETTINGS
    def test_local_ignored_for_lt(self, version: Version) -> None:
        """Local labels are stripped before comparison for < specifiers."""
        public = Version(str(version).split("+")[0])
        spec = Specifier(f"<{public}")
        assert version not in spec

    @given(spec_ver=release_versions(), local=st.integers(min_value=0, max_value=5))
    @SETTINGS
    def test_local_not_permitted_in_ordering_specifiers(
        self, spec_ver: Version, local: int
    ) -> None:
        """Local version identifiers must not be permitted in
        >=, <=, >, < specifiers."""
        local_str = f"+local{local}"
        for op in [">=", "<=", ">", "<"]:
            with pytest.raises(InvalidSpecifier):
                Specifier(f"{op}{spec_ver}{local_str}")


class TestCompatibleReleaseDefinition:
    """A compatible release clause consists of the compatible release operator ``~=``
    and a version identifier. It matches any candidate version that is expected
    to be compatible with the specified version."""

    @given(spec_ver=multi_segment_versions(), candidate=pep440_versions())
    @SETTINGS
    def test_compatible_release_matches_expected_compatible(
        self, spec_ver: Version, candidate: Version
    ) -> None:
        """~=V matches candidate iff candidate >= V and candidate matches the
        prefix wildcard derived from V."""
        assume(spec_ver.epoch == candidate.epoch)
        spec = Specifier(f"~={spec_ver}")
        result = candidate in spec
        # Also check via the expanded form
        release = spec_ver.release
        prefix = ".".join(str(s) for s in release[:-1])
        epoch_prefix = f"{spec_ver.epoch}!" if spec_ver.epoch else ""
        expanded = SpecifierSet(f">={spec_ver},=={epoch_prefix}{prefix}.*")
        expanded_result = candidate in expanded
        assert result == expanded_result


class TestCompatibleReleaseNoLocal:
    """The specified version identifier must be in the standard format described in
    `Version scheme`_. Local version identifiers are NOT permitted in this
    version specifier."""

    @given(spec_ver=release_versions(), local=st.integers(min_value=0, max_value=5))
    @SETTINGS
    def test_local_not_permitted_in_compatible(
        self, spec_ver: Version, local: int
    ) -> None:
        """~= with a local version identifier must raise InvalidSpecifier."""
        assume(len(spec_ver.release) >= 2)
        with pytest.raises(InvalidSpecifier):
            Specifier(f"~={spec_ver}+local{local}")


class TestCompatibleReleaseEquivalence:
    r"""For a given release identifier ``V.N``, the compatible release clause is
    approximately equivalent to the pair of comparison clauses::

        >= V.N, == V.*

    This operator MUST NOT be used with a single segment version number such as
    ``~=1``."""

    @given(
        major=small_ints,
        minor=small_ints,
        candidate=pep440_versions(),
    )
    @SETTINGS
    def test_two_segment_equivalence(
        self, major: int, minor: int, candidate: Version
    ) -> None:
        """~= V.N is equivalent to >= V.N, == V.* for two-segment versions."""
        v_str = f"{major}.{minor}"
        spec_compat = Specifier(f"~={v_str}")
        spec_expanded = SpecifierSet(f">={v_str},=={major}.*")
        assert (candidate in spec_compat) == (candidate in spec_expanded)

    @given(
        major=small_ints,
        minor=small_ints,
        patch=small_ints,
        candidate=pep440_versions(),
    )
    @SETTINGS
    def test_three_segment_equivalence(
        self, major: int, minor: int, patch: int, candidate: Version
    ) -> None:
        """~= V.N.P is equivalent to >= V.N.P, == V.N.*"""
        v_str = f"{major}.{minor}.{patch}"
        spec_compat = Specifier(f"~={v_str}")
        spec_expanded = SpecifierSet(f">={v_str},=={major}.{minor}.*")
        assert (candidate in spec_compat) == (candidate in spec_expanded)

    @given(major=small_ints)
    @SETTINGS
    def test_single_segment_rejected(self, major: int) -> None:
        """~= with a single segment version number must be rejected."""
        with pytest.raises(InvalidSpecifier):
            Specifier(f"~={major}")


class TestCompatibleReleaseSuffixIgnored:
    r"""If a pre-release, post-release or developmental release is named in a
    compatible release clause as ``V.N.suffix``, then the suffix is ignored
    when determining the required prefix match::

        ~= 2.2.post3
        >= 2.2.post3, == 2.*

        ~= 1.4.5a4
        >= 1.4.5a4, == 1.4.*"""

    @given(candidate=pep440_versions())
    @SETTINGS
    def test_post_release_suffix_ignored(self, candidate: Version) -> None:
        """~= 2.2.post3 is equivalent to >= 2.2.post3, == 2.*"""
        spec = Specifier("~=2.2.post3")
        expanded = SpecifierSet(">=2.2.post3,==2.*")
        assert (candidate in spec) == (candidate in expanded)

    @given(candidate=pep440_versions())
    @SETTINGS
    def test_pre_release_suffix_ignored(self, candidate: Version) -> None:
        """~= 1.4.5a4 is equivalent to >= 1.4.5a4, == 1.4.*"""
        spec = Specifier("~=1.4.5a4")
        expanded = SpecifierSet(">=1.4.5a4,==1.4.*")
        assert (candidate in spec) == (candidate in expanded)

    @given(
        base=multi_segment_versions(),
        post=small_ints,
        candidate=pep440_versions(),
    )
    @SETTINGS
    def test_post_suffix_general(
        self, base: Version, post: int, candidate: Version
    ) -> None:
        """~= V.N.postP uses V.* as the prefix (suffix ignored)."""
        assume(base.pre is None and base.post is None and base.dev is None)
        assume(len(base.release) >= 2)
        v_str = f"{base}.post{post}"
        release = base.release
        prefix = ".".join(str(s) for s in release[:-1])
        epoch_prefix = f"{base.epoch}!" if base.epoch else ""
        spec = Specifier(f"~={v_str}")
        expanded = SpecifierSet(f">={v_str},=={epoch_prefix}{prefix}.*")
        assert (candidate in spec) == (candidate in expanded)


class TestCompatibleReleasePaddingZeros:
    r"""The padding rules for release segment comparisons means that the assumed
    degree of forward compatibility in a compatible release clause can be
    controlled by appending additional zeros to the version specifier::

        ~= 2.2.0
        >= 2.2.0, == 2.2.*

        ~= 1.4.5.0
        >= 1.4.5.0, == 1.4.5.*"""

    @given(candidate=pep440_versions())
    @SETTINGS
    def test_padding_narrows_two_to_three(self, candidate: Version) -> None:
        """~= 2.2.0 is equivalent to >= 2.2.0, == 2.2.*"""
        spec = Specifier("~=2.2.0")
        expanded = SpecifierSet(">=2.2.0,==2.2.*")
        assert (candidate in spec) == (candidate in expanded)

    @given(candidate=pep440_versions())
    @SETTINGS
    def test_padding_narrows_three_to_four(self, candidate: Version) -> None:
        """~= 1.4.5.0 is equivalent to >= 1.4.5.0, == 1.4.5.*"""
        spec = Specifier("~=1.4.5.0")
        expanded = SpecifierSet(">=1.4.5.0,==1.4.5.*")
        assert (candidate in spec) == (candidate in expanded)

    @given(
        major=small_ints,
        minor=small_ints,
        candidate=pep440_versions(),
    )
    @SETTINGS
    def test_padding_zero_changes_prefix_depth(
        self, major: int, minor: int, candidate: Version
    ) -> None:
        """~= X.Y.0 matches a narrower set than ~= X.Y because the prefix
        is == X.Y.* instead of == X.*"""
        broad = Specifier(f"~={major}.{minor}")
        narrow = Specifier(f"~={major}.{minor}.0")
        if candidate in narrow:
            assert candidate in broad


class TestVersionMatchingStrict:
    r"""By default, the version matching operator is based on a strict equality
    comparison: the specified version must be exactly the same as the requested
    version. The *only* substitution performed is the zero padding of the
    release segment to ensure the release segments are compared with the same
    length."""

    @given(version=nonlocal_versions())
    @SETTINGS
    def test_version_matches_itself(self, version: Version) -> None:
        """== V always matches V."""
        spec = Specifier(f"=={version}")
        assert version in spec

    @given(version=release_versions())
    @SETTINGS
    def test_zero_padding_matches(self, version: Version) -> None:
        """== V.0 matches V due to zero padding (for final releases)."""
        padded_str = f"{version}.0"
        spec_from_padded = Specifier(f"=={padded_str}")
        assert version in spec_from_padded

    @given(version=release_versions())
    @SETTINGS
    def test_zero_padding_symmetric(self, version: Version) -> None:
        """If V matches == V.0, then V.0 matches == V."""
        padded = Version(f"{version}.0")
        spec_original = Specifier(f"=={version}")
        assert padded in spec_original


class TestVersionPrefixMatching:
    r"""Prefix matching may be requested instead of strict comparison, by appending
    a trailing ``.*`` to the version identifier in the version matching clause.
    This means that additional trailing segments will be ignored when
    determining whether or not a version identifier matches the clause. If the
    specified version includes only a release segment, then trailing components
    (or the lack thereof) in the release segment are also ignored."""

    @given(spec_ver=release_versions(), extra=small_ints)
    @SETTINGS
    def test_prefix_match_ignores_trailing_segments(
        self, spec_ver: Version, extra: int
    ) -> None:
        """== V.* matches V.extra for any extra segment."""
        spec = Specifier(f"=={spec_ver}.*")
        extended = Version(f"{spec_ver}.{extra}")
        assert extended in spec

    @given(spec_ver=release_versions())
    @SETTINGS
    def test_prefix_match_includes_exact(self, spec_ver: Version) -> None:
        """== V.* matches V itself (exact match is a prefix match)."""
        spec = Specifier(f"=={spec_ver}.*")
        assert spec_ver in spec

    @given(
        major=small_ints,
        minor=small_ints,
        patch=small_ints,
    )
    @SETTINGS
    def test_prefix_match_with_pre_release(
        self, major: int, minor: int, patch: int
    ) -> None:
        """== X.Y.* matches X.Y.Z.aN (pre-releases under the prefix)."""
        spec = Specifier(f"=={major}.{minor}.*")
        candidate = Version(f"{major}.{minor}.{patch}a1")
        assert candidate in spec

    @given(
        major=small_ints,
        minor=small_ints,
        post=small_ints,
    )
    @SETTINGS
    def test_prefix_match_with_post_release(
        self, major: int, minor: int, post: int
    ) -> None:
        """== X.Y.* matches X.Y.postN."""
        spec = Specifier(f"=={major}.{minor}.*")
        candidate = Version(f"{major}.{minor}.post{post}")
        assert candidate in spec


class TestVersionMatchingPost1Examples:
    r"""For example, given the version ``1.1.post1``, the following clauses would
    match or not as shown::

        == 1.1        # Not equal, so 1.1.post1 does not match clause
        == 1.1.post1  # Equal, so 1.1.post1 matches clause
        == 1.1.*      # Same prefix, so 1.1.post1 matches clause"""

    def test_strict_no_match(self) -> None:
        """== 1.1 does not match 1.1.post1."""
        assert Version("1.1.post1") not in Specifier("==1.1")

    def test_strict_exact_match(self) -> None:
        """== 1.1.post1 matches 1.1.post1."""
        assert Version("1.1.post1") in Specifier("==1.1.post1")

    def test_prefix_match(self) -> None:
        """== 1.1.* matches 1.1.post1."""
        assert Version("1.1.post1") in Specifier("==1.1.*")


class TestVersionMatchingAlphaExamples:
    r"""For purposes of prefix matching, the pre-release segment is considered to
    have an implied preceding ``.``, so given the version ``1.1a1``, the
    following clauses would match or not as shown::

        == 1.1        # Not equal, so 1.1a1 does not match clause
        == 1.1a1      # Equal, so 1.1a1 matches clause
        == 1.1.*      # Same prefix, so 1.1a1 matches clause
                      # if pre-releases are requested"""

    def test_strict_no_match(self) -> None:
        """== 1.1 does not match 1.1a1."""
        assert Version("1.1a1") not in Specifier("==1.1")

    def test_strict_exact_match(self) -> None:
        """== 1.1a1 matches 1.1a1."""
        assert Version("1.1a1") in Specifier("==1.1a1")

    def test_prefix_match_with_prereleases(self) -> None:
        """== 1.1.* matches 1.1a1 when pre-releases are requested."""
        spec = Specifier("==1.1.*")
        assert Version("1.1a1") in spec


class TestVersionMatchingExactExamples:
    r"""An exact match is also considered a prefix match (this interpretation is
    implied by the usual zero padding rules for the release segment of version
    identifiers). Given the version ``1.1``, the following clauses would
    match or not as shown::

        == 1.1        # Equal, so 1.1 matches clause
        == 1.1.0      # Zero padding expands 1.1 to 1.1.0, so it matches clause
        == 1.1.dev1   # Not equal (dev-release), so 1.1 does not match clause
        == 1.1a1      # Not equal (pre-release), so 1.1 does not match clause
        == 1.1.post1  # Not equal (post-release), so 1.1 does not match clause
        == 1.1.*      # Same prefix, so 1.1 matches clause"""

    def test_equal(self) -> None:
        """== 1.1 matches 1.1."""
        assert Version("1.1") in Specifier("==1.1")

    def test_zero_padding(self) -> None:
        """== 1.1.0 matches 1.1 via zero padding."""
        assert Version("1.1") in Specifier("==1.1.0")

    def test_dev_not_equal(self) -> None:
        """== 1.1.dev1 does not match 1.1."""
        assert Version("1.1") not in Specifier("==1.1.dev1")

    def test_pre_not_equal(self) -> None:
        """== 1.1a1 does not match 1.1."""
        assert Version("1.1") not in Specifier("==1.1a1")

    def test_post_not_equal(self) -> None:
        """== 1.1.post1 does not match 1.1."""
        assert Version("1.1") not in Specifier("==1.1.post1")

    def test_prefix_match(self) -> None:
        """== 1.1.* matches 1.1."""
        assert Version("1.1") in Specifier("==1.1.*")


class TestPrefixMatchInvalidForms:
    r"""It is invalid to have a prefix match containing a development or local release
    such as ``1.0.dev1.*`` or ``1.0+foo1.*``. If present, the development release
    segment is always the final segment in the public version, and the local version
    is ignored for comparison purposes, so using either in a prefix match wouldn't
    make any sense."""

    def test_dev_prefix_match_invalid(self) -> None:
        """== 1.0.dev1.* must be rejected."""
        with pytest.raises(InvalidSpecifier):
            Specifier("==1.0.dev1.*")

    def test_local_prefix_match_invalid(self) -> None:
        """== 1.0+foo1.* must be rejected."""
        with pytest.raises(InvalidSpecifier):
            Specifier("==1.0+foo1.*")

    @given(spec_ver=release_versions(), dev=small_ints)
    @SETTINGS
    def test_dev_prefix_match_invalid_general(
        self, spec_ver: Version, dev: int
    ) -> None:
        """== V.devN.* must always be rejected."""
        with pytest.raises(InvalidSpecifier):
            Specifier(f"=={spec_ver}.dev{dev}.*")


class TestLocalVersionMatchingPublic:
    r"""If the specified version identifier is a public version identifier (no
    local version label), then the local version label of any candidate versions
    MUST be ignored when matching versions."""

    @given(spec_ver=release_versions(), local=st.integers(min_value=0, max_value=5))
    @SETTINGS
    def test_public_specifier_ignores_local_label(
        self, spec_ver: Version, local: int
    ) -> None:
        """== V (public) matches V+localN because local label is ignored."""
        spec = Specifier(f"=={spec_ver}")
        candidate = Version(f"{spec_ver}+local{local}")
        assert candidate in spec

    @given(spec_ver=release_versions(), local=st.integers(min_value=0, max_value=5))
    @SETTINGS
    def test_public_wildcard_ignores_local_label(
        self, spec_ver: Version, local: int
    ) -> None:
        """== V.* (public) matches V.0+localN because local label is ignored."""
        spec = Specifier(f"=={spec_ver}.*")
        candidate = Version(f"{spec_ver}.0+local{local}")
        assert candidate in spec

    @given(
        spec_ver=release_versions(),
        local1=st.integers(min_value=0, max_value=5),
        local2=st.integers(min_value=0, max_value=5),
    )
    @SETTINGS
    def test_public_specifier_matches_any_local(
        self, spec_ver: Version, local1: int, local2: int
    ) -> None:
        """== V (public) matches V+localX for any local label."""
        spec = Specifier(f"=={spec_ver}")
        c1 = Version(f"{spec_ver}+local{local1}")
        c2 = Version(f"{spec_ver}+local{local2}")
        assert c1 in spec
        assert c2 in spec


class TestLocalVersionMatchingLocal:
    r"""If the specified version identifier is a local version identifier, then the
    local version labels of candidate versions MUST be considered when matching
    versions, with the public version identifier being matched as described
    above, and the local version label being checked for equivalence using a
    strict string equality comparison."""

    @given(spec_ver=release_versions(), local=st.integers(min_value=0, max_value=5))
    @SETTINGS
    def test_local_specifier_matches_same_local(
        self, spec_ver: Version, local: int
    ) -> None:
        """== V+localN matches V+localN (same local label)."""
        local_str = f"local{local}"
        spec = Specifier(f"=={spec_ver}+{local_str}")
        candidate = Version(f"{spec_ver}+{local_str}")
        assert candidate in spec

    @given(spec_ver=release_versions())
    @SETTINGS
    def test_local_specifier_does_not_match_different_local(
        self, spec_ver: Version
    ) -> None:
        """== V+local0 does not match V+local1 (different local label)."""
        spec = Specifier(f"=={spec_ver}+local0")
        candidate = Version(f"{spec_ver}+local1")
        assert candidate not in spec

    @given(spec_ver=release_versions(), local=st.integers(min_value=0, max_value=5))
    @SETTINGS
    def test_local_specifier_does_not_match_no_local(
        self, spec_ver: Version, local: int
    ) -> None:
        """== V+localN does not match V (no local label on candidate)."""
        spec = Specifier(f"=={spec_ver}+local{local}")
        assert spec_ver not in spec


class TestVersionExclusion:
    r"""A version exclusion clause includes the version exclusion operator ``!=``
    and a version identifier.

    The allowed version identifiers and comparison semantics are the same as
    those of the `Version matching`_ operator, except that the sense of any
    match is inverted."""

    @given(version=nonlocal_versions())
    @SETTINGS
    def test_exclusion_is_inverse_of_match(self, version: Version) -> None:
        """!= V is the logical inverse of == V for any version."""
        eq_spec = Specifier(f"=={version}")
        ne_spec = Specifier(f"!={version}")
        assert (version in eq_spec) != (version in ne_spec)

    @given(spec_ver=nonlocal_versions(), candidate=pep440_versions())
    @SETTINGS
    def test_exclusion_inverse_general(
        self, spec_ver: Version, candidate: Version
    ) -> None:
        """For any candidate, != V gives the opposite result of == V."""
        eq_spec = Specifier(f"=={spec_ver}")
        ne_spec = Specifier(f"!={spec_ver}")
        assert (candidate in eq_spec) != (candidate in ne_spec)

    @given(spec_ver=release_versions(), candidate=pep440_versions())
    @SETTINGS
    def test_prefix_exclusion_inverse(
        self, spec_ver: Version, candidate: Version
    ) -> None:
        """!= V.* is the inverse of == V.* for prefix matching."""
        eq_spec = Specifier(f"=={spec_ver}.*")
        ne_spec = Specifier(f"!={spec_ver}.*")
        assert (candidate in eq_spec) != (candidate in ne_spec)


class TestVersionExclusionPost1Examples:
    r"""For example, given the version ``1.1.post1``, the following clauses would
    match or not as shown::

        != 1.1        # Not equal, so 1.1.post1 matches clause
        != 1.1.post1  # Equal, so 1.1.post1 does not match clause
        != 1.1.*      # Same prefix, so 1.1.post1 does not match clause"""

    def test_not_equal_matches(self) -> None:
        """!= 1.1 matches 1.1.post1 (they are not equal)."""
        assert Version("1.1.post1") in Specifier("!=1.1")

    def test_equal_excludes(self) -> None:
        """!= 1.1.post1 does not match 1.1.post1 (they are equal)."""
        assert Version("1.1.post1") not in Specifier("!=1.1.post1")

    def test_prefix_excludes(self) -> None:
        """!= 1.1.* does not match 1.1.post1 (same prefix)."""
        assert Version("1.1.post1") not in Specifier("!=1.1.*")
