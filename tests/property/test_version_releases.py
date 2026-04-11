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
    pep440_versions,
    pre_tags,
    release_segment,
    small_ints,
)

pytestmark = pytest.mark.property


@st.composite
def final_versions(draw: st.DrawFn) -> Version:
    """Generate a final release version (release segment only, epoch optional)."""
    rel = draw(release_segment)
    epoch = draw(st.integers(min_value=0, max_value=3))
    if epoch > 0:
        return Version(f"{epoch}!{rel}")
    return Version(rel)


@st.composite
def pre_release_versions(draw: st.DrawFn) -> Version:
    """Generate a pre-release version (X.Y{a,b,rc}N)."""
    rel = draw(release_segment)
    phase = draw(pre_tags)
    num = draw(small_ints)
    return Version(f"{rel}{phase}{num}")


@st.composite
def post_release_versions(draw: st.DrawFn) -> Version:
    """Generate a post-release version (X.Y.postN)."""
    rel = draw(release_segment)
    post_num = draw(small_ints)
    return Version(f"{rel}.post{post_num}")


@st.composite
def dev_release_versions(draw: st.DrawFn) -> Version:
    """Generate a developmental release version (X.Y.devN)."""
    rel = draw(release_segment)
    dev_num = draw(small_ints)
    return Version(f"{rel}.dev{dev_num}")


# Pools of concrete versions for sampled_from strategies.
FINAL_POOL = [
    Version(s)
    for s in [
        "0.9",
        "0.9.1",
        "0.9.2",
        "0.9.10",
        "0.9.11",
        "1.0",
        "1.0.1",
        "1.1",
        "2.0",
        "2.0.1",
        "3.3.1",
        "3.3.5",
        "3.3.9.45",
        "2012.4",
        "2012.7",
        "2012.10",
        "2013.1",
        "2013.6",
    ]
]

PRE_POOL = [
    Version(s)
    for s in [
        "1.0a1",
        "1.0a2",
        "1.0b1",
        "1.0b2",
        "1.0rc1",
        "1.0rc2",
        "2.0a1",
        "2.0b1",
        "2.0rc1",
    ]
]

POST_POOL = [
    Version(s)
    for s in [
        "1.0.post0",
        "1.0.post1",
        "1.0.post2",
        "2.0.post1",
        "1.0a1.post1",
        "1.0b1.post1",
        "1.0rc1.post1",
    ]
]

DEV_POOL = [
    Version(s)
    for s in [
        "1.0.dev0",
        "1.0.dev1",
        "1.0.dev5",
        "2.0.dev0",
        "1.0a1.dev1",
        "1.0b1.dev1",
        "1.0rc1.dev1",
        "1.0.post1.dev1",
    ]
]

EPOCH_POOL = [
    Version(s)
    for s in [
        "1.0",
        "1.1",
        "2.0",
        "2013.10",
        "2014.04",
        "1!1.0",
        "1!1.1",
        "1!2.0",
        "2!1.0",
    ]
]


class TestFinalReleaseDefinition:
    """A version identifier that consists solely of a release segment and optionally
    an epoch identifier is termed a "final release"."""

    @given(version=final_versions())
    @SETTINGS
    def test_final_release_has_no_pre_post_dev(self, version: Version) -> None:
        """A final release has no pre, post, or dev segments."""
        assert version.pre is None
        assert version.post is None
        assert version.dev is None

    @given(version=final_versions())
    @SETTINGS
    def test_final_release_is_not_prerelease(self, version: Version) -> None:
        """A final release is not flagged as a pre-release."""
        assert not version.is_prerelease

    @given(version=final_versions())
    @SETTINGS
    def test_final_release_is_not_postrelease(self, version: Version) -> None:
        """A final release is not flagged as a post-release."""
        assert not version.is_postrelease

    @given(version=final_versions())
    @SETTINGS
    def test_final_release_is_not_devrelease(self, version: Version) -> None:
        """A final release is not flagged as a dev release."""
        assert not version.is_devrelease


class TestReleaseSegmentFormat:
    """The release segment consists of one or more non-negative integer
    values, separated by dots::

        N(.N)*"""

    @given(version=pep440_versions())
    @SETTINGS
    def test_release_tuple_is_non_negative(self, version: Version) -> None:
        """Each component of the release tuple is a non-negative integer."""
        for component in version.release:
            assert isinstance(component, int)
            assert component >= 0

    @given(version=pep440_versions())
    @SETTINGS
    def test_release_has_at_least_one_component(self, version: Version) -> None:
        """The release segment has at least one component."""
        assert len(version.release) >= 1


class TestReleaseSegmentComparison:
    """Comparison and ordering of release segments considers the numeric value
    of each component of the release segment in turn. When comparing release
    segments with different numbers of components, the shorter segment is
    padded out with additional zeros as necessary."""

    @given(
        major=small_ints,
        minor=small_ints,
    )
    @SETTINGS
    def test_zero_padding_two_vs_three(self, major: int, minor: int) -> None:
        """X.Y compares equal to X.Y.0 due to zero-padding."""
        v2 = Version(f"{major}.{minor}")
        v3 = Version(f"{major}.{minor}.0")
        assert v2 == v3

    @given(
        major=small_ints,
        minor=small_ints,
    )
    @SETTINGS
    def test_zero_padding_extended(self, major: int, minor: int) -> None:
        """X.Y compares equal to X.Y.0.0.0 due to zero-padding."""
        v2 = Version(f"{major}.{minor}")
        v5 = Version(f"{major}.{minor}.0.0.0")
        assert v2 == v5

    @given(
        version_a=st.sampled_from(FINAL_POOL),
        version_b=st.sampled_from(FINAL_POOL),
    )
    @SETTINGS
    def test_component_wise_ordering(
        self, version_a: Version, version_b: Version
    ) -> None:
        """Ordering is determined by comparing components left to right."""
        # Pad both release tuples to the same length for comparison.
        len_max = max(len(version_a.release), len(version_b.release))
        a_padded = version_a.release + (0,) * (len_max - len(version_a.release))
        b_padded = version_b.release + (0,) * (len_max - len(version_b.release))
        assert (version_a < version_b) == (a_padded < b_padded)
        assert (version_a == version_b) == (a_padded == b_padded)

    @given(
        components=st.lists(small_ints, min_size=1, max_size=5),
        extra_zeros=st.integers(min_value=1, max_value=4),
    )
    @SETTINGS
    def test_trailing_zeros_are_ignored(
        self, components: list[int], extra_zeros: int
    ) -> None:
        """Trailing zeros do not change the version identity."""
        base = ".".join(str(c) for c in components)
        extended = base + ".0" * extra_zeros
        assert Version(base) == Version(extended)


class TestFinalReleaseExampleOrdering:
    r"""For example::

    0.9
    0.9.1
    0.9.2
    ...
    0.9.10
    0.9.11
    1.0
    1.0.1
    1.1
    2.0
    2.0.1
    ..."""

    @SETTINGS
    @given(data=st.data())
    def test_example_sequence_is_sorted(self, data: st.DataObject) -> None:
        """Any two versions from the example list are ordered correctly."""
        versions = [
            Version("0.9"),
            Version("0.9.1"),
            Version("0.9.2"),
            Version("0.9.10"),
            Version("0.9.11"),
            Version("1.0"),
            Version("1.0.1"),
            Version("1.1"),
            Version("2.0"),
            Version("2.0.1"),
        ]
        i = data.draw(st.integers(min_value=0, max_value=len(versions) - 1))
        j = data.draw(st.integers(min_value=0, max_value=len(versions) - 1))
        if i < j:
            assert versions[i] < versions[j]
        elif i == j:
            assert versions[i] == versions[j]
        else:
            assert versions[i] > versions[j]


class TestXYEqualsXY0:
    """.. note::

    ``X.Y`` and ``X.Y.0`` are not considered distinct release numbers, as
    the release segment comparison rules implicitly expand the two component
    form to ``X.Y.0`` when comparing it to any release segment that includes
    three components."""

    @given(major=small_ints, minor=small_ints)
    @SETTINGS
    def test_xy_equals_xy0(self, major: int, minor: int) -> None:
        """X.Y == X.Y.0."""
        assert Version(f"{major}.{minor}") == Version(f"{major}.{minor}.0")

    @given(major=small_ints, minor=small_ints)
    @SETTINGS
    def test_xy_hash_equals_xy0_hash(self, major: int, minor: int) -> None:
        """hash(X.Y) == hash(X.Y.0) since they are equal."""
        assert hash(Version(f"{major}.{minor}")) == hash(Version(f"{major}.{minor}.0"))

    @given(major=small_ints, minor=small_ints, micro=small_ints)
    @SETTINGS
    def test_specifier_match_equivalent(
        self, major: int, minor: int, micro: int
    ) -> None:
        """X.Y and X.Y.0 match the same specifiers involving
        three-component versions."""
        v2 = Version(f"{major}.{minor}")
        v3 = Version(f"{major}.{minor}.0")
        spec = SpecifierSet(f">={major}.{minor}.{micro}")
        assert (v2 in spec) == (v3 in spec)


class TestDateBasedReleases:
    """Date-based release segments are also permitted. An example of a date-based
    release scheme using the year and month of the release::

        2012.4
        2012.7
        2012.10
        2013.1
        2013.6
        ..."""

    @SETTINGS
    @given(data=st.data())
    def test_date_based_example_ordering(self, data: st.DataObject) -> None:
        """The example date-based versions are in strictly increasing order."""
        versions = [
            Version("2012.4"),
            Version("2012.7"),
            Version("2012.10"),
            Version("2013.1"),
            Version("2013.6"),
        ]
        i = data.draw(st.integers(min_value=0, max_value=len(versions) - 1))
        j = data.draw(st.integers(min_value=0, max_value=len(versions) - 1))
        if i < j:
            assert versions[i] < versions[j]
        elif i == j:
            assert versions[i] == versions[j]
        else:
            assert versions[i] > versions[j]

    @given(
        year=st.integers(min_value=2000, max_value=2030),
        month=st.integers(min_value=1, max_value=12),
    )
    @SETTINGS
    def test_date_based_versions_are_valid(self, year: int, month: int) -> None:
        """Date-based versions parse as valid PEP 440 versions."""
        v = Version(f"{year}.{month}")
        assert v.release == (year, month)
        assert v.epoch == 0


class TestPreReleaseIndicators:
    r"""If used as part of a project's development cycle, these pre-releases are
    indicated by including a pre-release segment in the version identifier::

        X.YaN   # Alpha release
        X.YbN   # Beta release
        X.YrcN  # Release Candidate
        X.Y     # Final release"""

    @given(version=pre_release_versions())
    @SETTINGS
    def test_pre_release_has_pre_segment(self, version: Version) -> None:
        """A pre-release version has a non-None pre attribute."""
        assert version.pre is not None

    @given(version=pre_release_versions())
    @SETTINGS
    def test_pre_release_phase_is_valid(self, version: Version) -> None:
        """The pre-release phase is one of a, b, or rc."""
        assert version.pre is not None
        phase, _ = version.pre
        assert phase in ("a", "b", "rc")

    @given(
        major=small_ints,
        minor=small_ints,
        phase=pre_tags,
        num=small_ints,
    )
    @SETTINGS
    def test_pre_release_before_final(
        self, major: int, minor: int, phase: str, num: int
    ) -> None:
        """Any pre-release X.Y{a,b,rc}N sorts before the final release X.Y."""
        pre = Version(f"{major}.{minor}{phase}{num}")
        final = Version(f"{major}.{minor}")
        assert pre < final


class TestPreReleaseDefinition:
    """A version identifier that consists solely of a release segment and a
    pre-release segment is termed a "pre-release"."""

    @given(version=pre_release_versions())
    @SETTINGS
    def test_pre_release_is_prerelease(self, version: Version) -> None:
        """A pre-release version has is_prerelease == True."""
        assert version.is_prerelease

    @given(version=pre_release_versions())
    @SETTINGS
    def test_pre_release_is_not_postrelease(self, version: Version) -> None:
        """A bare pre-release is not a post-release."""
        assert not version.is_postrelease

    @given(version=pre_release_versions())
    @SETTINGS
    def test_pre_release_is_not_devrelease(self, version: Version) -> None:
        """A bare pre-release is not a dev release."""
        assert not version.is_devrelease


class TestPreReleasePhaseOrdering:
    """The pre-release segment consists of an alphabetical identifier for the
    pre-release phase, along with a non-negative integer value. Pre-releases for
    a given release are ordered first by phase (alpha, beta, release candidate)
    and then by the numerical component within that phase."""

    @given(
        major=small_ints,
        minor=small_ints,
        num=small_ints,
    )
    @SETTINGS
    def test_alpha_before_beta(self, major: int, minor: int, num: int) -> None:
        """Alpha comes before beta for the same release and number."""
        alpha = Version(f"{major}.{minor}a{num}")
        beta = Version(f"{major}.{minor}b{num}")
        assert alpha < beta

    @given(
        major=small_ints,
        minor=small_ints,
        num=small_ints,
    )
    @SETTINGS
    def test_beta_before_rc(self, major: int, minor: int, num: int) -> None:
        """Beta comes before release candidate for the same release and number."""
        beta = Version(f"{major}.{minor}b{num}")
        rc = Version(f"{major}.{minor}rc{num}")
        assert beta < rc

    @given(
        major=small_ints,
        minor=small_ints,
        num=small_ints,
    )
    @SETTINGS
    def test_alpha_before_rc(self, major: int, minor: int, num: int) -> None:
        """Alpha comes before release candidate for the same release and number."""
        alpha = Version(f"{major}.{minor}a{num}")
        rc = Version(f"{major}.{minor}rc{num}")
        assert alpha < rc

    @given(
        major=small_ints,
        minor=small_ints,
        phase=pre_tags,
        number_a=small_ints,
        number_b=small_ints,
    )
    @SETTINGS
    def test_numerical_ordering_within_phase(
        self, major: int, minor: int, phase: str, number_a: int, number_b: int
    ) -> None:
        """Within the same phase, ordering is by the numerical component."""
        assume(number_a != number_b)
        v1 = Version(f"{major}.{minor}{phase}{number_a}")
        v2 = Version(f"{major}.{minor}{phase}{number_b}")
        assert (v1 < v2) == (number_a < number_b)


class TestCEquivalentToRc:
    """Installation tools MAY accept both ``c`` and ``rc`` releases for a common
    release segment in order to handle some existing legacy distributions."""

    @given(
        major=small_ints,
        minor=small_ints,
        num=small_ints,
    )
    @SETTINGS
    def test_c_parses_as_rc(self, major: int, minor: int, num: int) -> None:
        """A 'c' pre-release is accepted and parsed as 'rc'."""
        v = Version(f"{major}.{minor}c{num}")
        assert v.pre is not None
        assert v.pre[0] == "rc"


class TestCVersionEquivalence:
    """Installation tools SHOULD interpret ``c`` versions as being equivalent to
    ``rc`` versions (that is, ``c1`` indicates the same version as ``rc1``)."""

    @given(
        major=small_ints,
        minor=small_ints,
        num=small_ints,
    )
    @SETTINGS
    def test_c_equals_rc(self, major: int, minor: int, num: int) -> None:
        """Version('X.YcN') == Version('X.YrcN')."""
        c_ver = Version(f"{major}.{minor}c{num}")
        rc_ver = Version(f"{major}.{minor}rc{num}")
        assert c_ver == rc_ver

    @given(
        major=small_ints,
        minor=small_ints,
        num=small_ints,
    )
    @SETTINGS
    def test_c_hash_equals_rc_hash(self, major: int, minor: int, num: int) -> None:
        """hash(Version('X.YcN')) == hash(Version('X.YrcN'))."""
        c_ver = Version(f"{major}.{minor}c{num}")
        rc_ver = Version(f"{major}.{minor}rc{num}")
        assert hash(c_ver) == hash(rc_ver)


class TestPostReleaseIndicator:
    """If used as part of a project's development cycle, these post-releases are
    indicated by including a post-release segment in the version identifier::

        X.Y.postN    # Post-release"""

    @given(version=post_release_versions())
    @SETTINGS
    def test_post_release_has_post_segment(self, version: Version) -> None:
        """A post-release version has a non-None post attribute."""
        assert version.post is not None

    @given(
        major=small_ints,
        minor=small_ints,
        post_num=small_ints,
    )
    @SETTINGS
    def test_post_release_string_contains_post(
        self, major: int, minor: int, post_num: int
    ) -> None:
        """The string representation contains '.postN'."""
        v = Version(f"{major}.{minor}.post{post_num}")
        assert f".post{post_num}" in str(v)


class TestPostReleaseDefinition:
    """A version identifier that includes a post-release segment without a
    developmental release segment is termed a "post-release"."""

    @given(version=post_release_versions())
    @SETTINGS
    def test_post_release_is_postrelease(self, version: Version) -> None:
        """A post-release has is_postrelease == True."""
        assert version.is_postrelease

    @given(version=post_release_versions())
    @SETTINGS
    def test_post_release_is_not_devrelease(self, version: Version) -> None:
        """A bare post-release is not a dev release."""
        assert not version.is_devrelease


class TestPostReleaseOrdering:
    """The post-release segment consists of the string ``.post``, followed by a
    non-negative integer value. Post-releases are ordered by their
    numerical component, immediately following the corresponding release,
    and ahead of any subsequent release."""

    @given(
        major=small_ints,
        minor=small_ints,
        number_a=small_ints,
        number_b=small_ints,
    )
    @SETTINGS
    def test_post_numerical_ordering(
        self, major: int, minor: int, number_a: int, number_b: int
    ) -> None:
        """Post-releases are ordered by their numerical component."""
        assume(number_a != number_b)
        v1 = Version(f"{major}.{minor}.post{number_a}")
        v2 = Version(f"{major}.{minor}.post{number_b}")
        assert (v1 < v2) == (number_a < number_b)

    @given(
        major=small_ints,
        minor=small_ints,
        post_num=st.integers(min_value=0, max_value=20),
    )
    @SETTINGS
    def test_post_release_after_final(
        self, major: int, minor: int, post_num: int
    ) -> None:
        """A post-release immediately follows its corresponding final release."""
        final = Version(f"{major}.{minor}")
        post = Version(f"{major}.{minor}.post{post_num}")
        assert post > final

    @given(
        major=small_ints,
        minor=small_ints,
        post_num=small_ints,
        next_micro=st.integers(min_value=1, max_value=20),
    )
    @SETTINGS
    def test_post_release_before_subsequent_release(
        self, major: int, minor: int, post_num: int, next_micro: int
    ) -> None:
        """A post-release comes before any subsequent release."""
        post = Version(f"{major}.{minor}.post{post_num}")
        subsequent = Version(f"{major}.{minor}.{next_micro}")
        assert post < subsequent


class TestPostReleasesOfPreReleases:
    r"""Post-releases are also permitted for pre-releases::

    X.YaN.postM   # Post-release of an alpha release
    X.YbN.postM   # Post-release of a beta release
    X.YrcN.postM  # Post-release of a release candidate"""

    @given(
        major=small_ints,
        minor=small_ints,
        phase=pre_tags,
        pre_num=small_ints,
        post_num=small_ints,
    )
    @SETTINGS
    def test_post_of_pre_is_valid(
        self, major: int, minor: int, phase: str, pre_num: int, post_num: int
    ) -> None:
        """Post-releases of pre-releases parse successfully."""
        v = Version(f"{major}.{minor}{phase}{pre_num}.post{post_num}")
        assert v.pre is not None
        assert v.pre[0] == phase
        assert v.pre[1] == pre_num
        assert v.post == post_num

    @given(
        major=small_ints,
        minor=small_ints,
        phase=pre_tags,
        pre_num=small_ints,
        post_num=small_ints,
    )
    @SETTINGS
    def test_post_of_pre_after_pre(
        self, major: int, minor: int, phase: str, pre_num: int, post_num: int
    ) -> None:
        """A post-release of a pre-release sorts after the pre-release itself."""
        pre = Version(f"{major}.{minor}{phase}{pre_num}")
        post_of_pre = Version(f"{major}.{minor}{phase}{pre_num}.post{post_num}")
        assert post_of_pre > pre

    @given(
        major=small_ints,
        minor=small_ints,
        phase=pre_tags,
        pre_num=small_ints,
        post_num=small_ints,
    )
    @SETTINGS
    def test_post_of_pre_is_postrelease(
        self, major: int, minor: int, phase: str, pre_num: int, post_num: int
    ) -> None:
        """A post-release of a pre-release is flagged as both pre and post."""
        v = Version(f"{major}.{minor}{phase}{pre_num}.post{post_num}")
        assert v.is_prerelease
        assert v.is_postrelease


class TestDevReleaseIndicator:
    """If used as part of a project's development cycle, these developmental
    releases are indicated by including a developmental release segment in the
    version identifier::

        X.Y.devN    # Developmental release"""

    @given(version=dev_release_versions())
    @SETTINGS
    def test_dev_release_has_dev_segment(self, version: Version) -> None:
        """A developmental release has a non-None dev attribute."""
        assert version.dev is not None

    @given(
        major=small_ints,
        minor=small_ints,
        dev_num=small_ints,
    )
    @SETTINGS
    def test_dev_release_string_contains_dev(
        self, major: int, minor: int, dev_num: int
    ) -> None:
        """The string representation contains '.devN'."""
        v = Version(f"{major}.{minor}.dev{dev_num}")
        assert f".dev{dev_num}" in str(v)


class TestDevReleaseDefinition:
    """A version identifier that includes a developmental release segment is
    termed a "developmental release"."""

    @given(version=dev_release_versions())
    @SETTINGS
    def test_dev_release_is_devrelease(self, version: Version) -> None:
        """A developmental release has is_devrelease == True."""
        assert version.is_devrelease


class TestDevReleaseOrdering:
    """The developmental release segment consists of the string ``.dev``,
    followed by a non-negative integer value. Developmental releases are ordered
    by their numerical component, immediately before the corresponding release
    (and before any pre-releases with the same release segment), and following
    any previous release (including any post-releases)."""

    @given(
        major=small_ints,
        minor=small_ints,
        number_a=small_ints,
        number_b=small_ints,
    )
    @SETTINGS
    def test_dev_numerical_ordering(
        self, major: int, minor: int, number_a: int, number_b: int
    ) -> None:
        """Dev releases are ordered by their numerical component."""
        assume(number_a != number_b)
        v1 = Version(f"{major}.{minor}.dev{number_a}")
        v2 = Version(f"{major}.{minor}.dev{number_b}")
        assert (v1 < v2) == (number_a < number_b)

    @given(
        major=small_ints,
        minor=small_ints,
        dev_num=small_ints,
    )
    @SETTINGS
    def test_dev_before_corresponding_release(
        self, major: int, minor: int, dev_num: int
    ) -> None:
        """A dev release sorts before its corresponding final release."""
        dev = Version(f"{major}.{minor}.dev{dev_num}")
        final = Version(f"{major}.{minor}")
        assert dev < final

    @given(
        major=small_ints,
        minor=small_ints,
        dev_num=small_ints,
        phase=pre_tags,
        pre_num=small_ints,
    )
    @SETTINGS
    def test_dev_before_pre_releases(
        self, major: int, minor: int, dev_num: int, phase: str, pre_num: int
    ) -> None:
        """A dev release sorts before any pre-release with the same release segment."""
        dev = Version(f"{major}.{minor}.dev{dev_num}")
        pre = Version(f"{major}.{minor}{phase}{pre_num}")
        assert dev < pre

    @given(
        major=small_ints,
        minor=small_ints,
        dev_num=small_ints,
        prev_micro=st.integers(min_value=0, max_value=20),
        prev_post=small_ints,
    )
    @SETTINGS
    def test_dev_after_previous_post_release(
        self, major: int, minor: int, dev_num: int, prev_micro: int, prev_post: int
    ) -> None:
        """A dev release follows any previous release including post-releases.

        For X.Y.Z.devN, the previous release segment is X.Y.(Z-1). We test
        that X.Y.1.devN > X.Y.0.postM.
        """
        # Use a concrete case: X.Y.1.devN should be after X.Y.0.postM
        prev = Version(f"{major}.{minor}.{prev_micro}.post{prev_post}")
        dev = Version(f"{major}.{minor}.{prev_micro + 1}.dev{dev_num}")
        assert dev > prev


class TestDevReleasesOfPreAndPost:
    r"""Developmental releases are also permitted for pre-releases and
    post-releases::

        X.YaN.devM       # Developmental release of an alpha release
        X.YbN.devM       # Developmental release of a beta release
        X.YrcN.devM      # Developmental release of a release candidate
        X.Y.postN.devM   # Developmental release of a post-release"""

    @given(
        major=small_ints,
        minor=small_ints,
        phase=pre_tags,
        pre_num=small_ints,
        dev_num=small_ints,
    )
    @SETTINGS
    def test_dev_of_pre_is_valid(
        self, major: int, minor: int, phase: str, pre_num: int, dev_num: int
    ) -> None:
        """Dev releases of pre-releases parse successfully."""
        v = Version(f"{major}.{minor}{phase}{pre_num}.dev{dev_num}")
        assert v.pre is not None
        assert v.pre[0] == phase
        assert v.pre[1] == pre_num
        assert v.dev == dev_num

    @given(
        major=small_ints,
        minor=small_ints,
        post_num=small_ints,
        dev_num=small_ints,
    )
    @SETTINGS
    def test_dev_of_post_is_valid(
        self, major: int, minor: int, post_num: int, dev_num: int
    ) -> None:
        """Dev releases of post-releases parse successfully."""
        v = Version(f"{major}.{minor}.post{post_num}.dev{dev_num}")
        assert v.post == post_num
        assert v.dev == dev_num

    @given(
        major=small_ints,
        minor=small_ints,
        phase=pre_tags,
        pre_num=small_ints,
        dev_num=small_ints,
    )
    @SETTINGS
    def test_dev_of_pre_before_pre(
        self, major: int, minor: int, phase: str, pre_num: int, dev_num: int
    ) -> None:
        """A dev release of a pre-release sorts before the pre-release itself."""
        dev_of_pre = Version(f"{major}.{minor}{phase}{pre_num}.dev{dev_num}")
        pre = Version(f"{major}.{minor}{phase}{pre_num}")
        assert dev_of_pre < pre

    @given(
        major=small_ints,
        minor=small_ints,
        post_num=small_ints,
        dev_num=small_ints,
    )
    @SETTINGS
    def test_dev_of_post_before_post(
        self, major: int, minor: int, post_num: int, dev_num: int
    ) -> None:
        """A dev release of a post-release sorts before the post-release itself."""
        dev_of_post = Version(f"{major}.{minor}.post{post_num}.dev{dev_num}")
        post = Version(f"{major}.{minor}.post{post_num}")
        assert dev_of_post < post


class TestDevReleasesArePreReleases:
    """Do note that development releases are considered a type of pre-release when
    handling them."""

    @given(version=dev_release_versions())
    @SETTINGS
    def test_dev_is_prerelease(self, version: Version) -> None:
        """A dev release has is_prerelease == True."""
        assert version.is_prerelease

    @given(
        major=small_ints,
        minor=small_ints,
        dev_num=small_ints,
    )
    @SETTINGS
    def test_dev_excluded_by_default_from_specifier(
        self, major: int, minor: int, dev_num: int
    ) -> None:
        """Dev releases are excluded from specifier matching by default
        (since they are pre-releases)."""
        dev = Version(f"{major}.{minor}.dev{dev_num}")
        spec = SpecifierSet(f">={major}.{minor}.dev0")
        # When prereleases=False (the default behavior for non-pre specifiers),
        # dev releases should be excluded. But a specifier that itself references
        # a pre-release enables pre-release matching.
        assert dev in spec

    @given(
        major=small_ints,
        minor=small_ints,
        dev_num=small_ints,
    )
    @SETTINGS
    def test_dev_excluded_by_non_pre_specifier(
        self, major: int, minor: int, dev_num: int
    ) -> None:
        """Dev releases are excluded from a non-pre-release specifier by default."""
        dev = Version(f"{major}.{minor}.dev{dev_num}")
        # Use a specifier that does not reference pre-releases.
        spec = Specifier(f">={major}.{minor}")
        # With prereleases not explicitly set, dev releases should be excluded.
        assert not spec.contains(dev)


class TestEpochFormat:
    """If included in a version identifier, the epoch appears before all other
    components, separated from the release segment by an exclamation mark::

        E!X.Y  # Version identifier with epoch"""

    @given(
        epoch=st.integers(min_value=1, max_value=10),
        major=small_ints,
        minor=small_ints,
    )
    @SETTINGS
    def test_epoch_parsed_correctly(self, epoch: int, major: int, minor: int) -> None:
        """The epoch is parsed from E!X.Y format."""
        v = Version(f"{epoch}!{major}.{minor}")
        assert v.epoch == epoch
        assert v.release == (major, minor)

    @given(
        epoch=st.integers(min_value=1, max_value=10),
        major=small_ints,
        minor=small_ints,
    )
    @SETTINGS
    def test_epoch_in_string_representation(
        self, epoch: int, major: int, minor: int
    ) -> None:
        """The string representation includes the epoch when non-zero."""
        v = Version(f"{epoch}!{major}.{minor}")
        assert str(v).startswith(f"{epoch}!")


class TestImplicitEpochZero:
    """If no explicit epoch is given, the implicit epoch is ``0``."""

    @given(version=pep440_versions())
    @SETTINGS
    def test_no_epoch_means_zero(self, version: Version) -> None:
        """Versions without an explicit epoch have epoch == 0."""
        assume("!" not in str(version))
        assert version.epoch == 0

    @given(major=small_ints, minor=small_ints)
    @SETTINGS
    def test_explicit_zero_epoch_equals_implicit(self, major: int, minor: int) -> None:
        """0!X.Y is equivalent to X.Y."""
        explicit = Version(f"0!{major}.{minor}")
        implicit = Version(f"{major}.{minor}")
        assert explicit == implicit

    @given(major=small_ints, minor=small_ints)
    @SETTINGS
    def test_explicit_zero_epoch_hash(self, major: int, minor: int) -> None:
        """hash(0!X.Y) == hash(X.Y)."""
        explicit = Version(f"0!{major}.{minor}")
        implicit = Version(f"{major}.{minor}")
        assert hash(explicit) == hash(implicit)


class TestEpochMotivation:
    """Most version identifiers will not include an epoch, as an explicit epoch is
    only needed if a project *changes* the way it handles version numbering in
    a way that means the normal version ordering rules will give the wrong
    answer. For example, if a project is using date based versions like
    ``2014.04`` and would like to switch to semantic versions like ``1.0``, then
    the new releases would be identified as *older* than the date based releases
    when using the normal sorting scheme::

        1.0
        1.1
        2.0
        2013.10
        2014.04"""

    @SETTINGS
    @given(data=st.data())
    def test_without_epoch_date_sorts_after_semver(self, data: st.DataObject) -> None:
        """Without epochs, date-based versions sort after smaller semver versions."""
        versions = [
            Version("1.0"),
            Version("1.1"),
            Version("2.0"),
            Version("2013.10"),
            Version("2014.04"),
        ]
        i = data.draw(st.integers(min_value=0, max_value=len(versions) - 1))
        j = data.draw(st.integers(min_value=0, max_value=len(versions) - 1))
        if i < j:
            assert versions[i] < versions[j]
        elif i == j:
            assert versions[i] == versions[j]
        else:
            assert versions[i] > versions[j]


class TestEpochReorderingExample:
    """However, by specifying an explicit epoch, the sort order can be changed
    appropriately, as all versions from a later epoch are sorted after versions
    from an earlier epoch::

        2013.10
        2014.04
        1!1.0
        1!1.1
        1!2.0"""

    @SETTINGS
    @given(data=st.data())
    def test_epoch_example_ordering(self, data: st.DataObject) -> None:
        """The example with epochs produces the expected ordering."""
        versions = [
            Version("2013.10"),
            Version("2014.04"),
            Version("1!1.0"),
            Version("1!1.1"),
            Version("1!2.0"),
        ]
        i = data.draw(st.integers(min_value=0, max_value=len(versions) - 1))
        j = data.draw(st.integers(min_value=0, max_value=len(versions) - 1))
        if i < j:
            assert versions[i] < versions[j]
        elif i == j:
            assert versions[i] == versions[j]
        else:
            assert versions[i] > versions[j]

    @given(
        epoch_a=st.integers(min_value=0, max_value=5),
        epoch_b=st.integers(min_value=0, max_value=5),
        rel_a=st.tuples(small_ints, small_ints),
        rel_b=st.tuples(small_ints, small_ints),
    )
    @SETTINGS
    def test_later_epoch_always_greater(
        self,
        epoch_a: int,
        epoch_b: int,
        rel_a: tuple[int, int],
        rel_b: tuple[int, int],
    ) -> None:
        """All versions from a later epoch sort after versions from an earlier epoch."""
        assume(epoch_a != epoch_b)
        va_str = (
            f"{rel_a[0]}.{rel_a[1]}"
            if epoch_a == 0
            else f"{epoch_a}!{rel_a[0]}.{rel_a[1]}"
        )
        vb_str = (
            f"{rel_b[0]}.{rel_b[1]}"
            if epoch_b == 0
            else f"{epoch_b}!{rel_b[0]}.{rel_b[1]}"
        )
        va = Version(va_str)
        vb = Version(vb_str)
        if epoch_a < epoch_b:
            assert va < vb
        else:
            assert va > vb
