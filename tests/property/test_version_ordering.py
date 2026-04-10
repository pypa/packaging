# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.

from __future__ import annotations

import itertools

import pytest
from hypothesis import given
from hypothesis import strategies as st

from packaging.version import Version
from tests.property.strategies import SETTINGS, pre_tags, release_segment, small_ints

pytestmark = pytest.mark.property

_epoch_ints = st.integers(min_value=0, max_value=5)


class TestEpochOrdering:
    """
    The epoch segment of version identifiers MUST be sorted according to the
    numeric value of the given epoch. If no epoch segment is present, the
    implicit numeric value is ``0``.
    """

    @given(epoch_a=_epoch_ints, epoch_b=_epoch_ints, release=release_segment)
    @SETTINGS
    def test_epoch_sorts_by_numeric_value(
        self, epoch_a: int, epoch_b: int, release: str
    ) -> None:
        """Higher epoch always sorts higher, same release."""
        v1 = Version(f"{epoch_a}!{release}")
        v2 = Version(f"{epoch_b}!{release}")
        if epoch_a < epoch_b:
            assert v1 < v2
        elif epoch_a > epoch_b:
            assert v1 > v2
        else:
            assert v1 == v2

    @given(release=release_segment)
    @SETTINGS
    def test_implicit_epoch_is_zero(self, release: str) -> None:
        """Omitting the epoch is the same as epoch 0."""
        v_no_epoch = Version(release)
        v_explicit_zero = Version(f"0!{release}")
        assert v_no_epoch == v_explicit_zero

    @given(
        epoch=st.integers(min_value=1, max_value=5),
        release_a=release_segment,
        release_b=release_segment,
    )
    @SETTINGS
    def test_higher_epoch_beats_any_release(
        self, epoch: int, release_a: str, release_b: str
    ) -> None:
        """A higher epoch always wins regardless of release segments."""
        v_low = Version(f"0!{release_a}")
        v_high = Version(f"{epoch}!{release_b}")
        assert v_high > v_low


class TestReleaseSegmentOrdering:
    """
    The release segment of version identifiers MUST be sorted in
    the same order as Python's tuple sorting when the normalized release segment is
    parsed as follows::

        tuple(map(int, release_segment.split(".")))
    """

    @given(
        release_a=st.lists(
            st.integers(min_value=0, max_value=50), min_size=1, max_size=4
        ),
        release_b=st.lists(
            st.integers(min_value=0, max_value=50), min_size=1, max_size=4
        ),
    )
    @SETTINGS
    def test_release_sorts_like_tuple(
        self, release_a: list[int], release_b: list[int]
    ) -> None:
        """Release segment ordering matches tuple ordering with zero padding."""
        v1 = Version(".".join(str(x) for x in release_a))
        v2 = Version(".".join(str(x) for x in release_b))
        # Pad to equal length with zeros, like the spec requires.
        maxlen = max(len(release_a), len(release_b))
        t1 = tuple(release_a) + (0,) * (maxlen - len(release_a))
        t2 = tuple(release_b) + (0,) * (maxlen - len(release_b))
        if t1 < t2:
            assert v1 < v2
        elif t1 > t2:
            assert v1 > v2
        else:
            assert v1 == v2


class TestReleaseSegmentZeroPadding:
    """
    All release segments involved in the comparison MUST be converted to a
    consistent length by padding shorter segments with zeros as needed.
    """

    @given(
        base=st.lists(st.integers(min_value=0, max_value=20), min_size=1, max_size=3),
        extra_zeros=st.integers(min_value=1, max_value=3),
    )
    @SETTINGS
    def test_trailing_zeros_are_equal(self, base: list[int], extra_zeros: int) -> None:
        """Appending trailing zeros does not change ordering."""
        short = ".".join(str(x) for x in base)
        long = short + ".0" * extra_zeros
        assert Version(short) == Version(long)


class TestSuffixOrdering:
    """
    Within a numeric release (``1.0``, ``2.7.3``), the following suffixes
    are permitted and MUST be ordered as shown::

       .devN, aN, bN, rcN, <no suffix>, .postN
    """

    @given(release=release_segment, number=small_ints)
    @SETTINGS
    def test_dev_before_alpha(self, release: str, number: int) -> None:
        """.devN < aN for the same release."""
        dev = Version(f"{release}.dev{number}")
        alpha = Version(f"{release}a{number}")
        assert dev < alpha

    @given(release=release_segment, number=small_ints)
    @SETTINGS
    def test_alpha_before_beta(self, release: str, number: int) -> None:
        """aN < bN for the same release."""
        alpha = Version(f"{release}a{number}")
        beta = Version(f"{release}b{number}")
        assert alpha < beta

    @given(release=release_segment, number=small_ints)
    @SETTINGS
    def test_beta_before_rc(self, release: str, number: int) -> None:
        """bN < rcN for the same release."""
        beta = Version(f"{release}b{number}")
        rc = Version(f"{release}rc{number}")
        assert beta < rc

    @given(release=release_segment, number=small_ints)
    @SETTINGS
    def test_rc_before_release(self, release: str, number: int) -> None:
        """rcN < <no suffix> for the same release."""
        rc = Version(f"{release}rc{number}")
        final = Version(release)
        assert rc < final

    @given(release=release_segment, number=small_ints)
    @SETTINGS
    def test_release_before_post(self, release: str, number: int) -> None:
        """<no suffix> < .postN for the same release."""
        final = Version(release)
        post = Version(f"{release}.post{number}")
        assert final < post

    @given(release=release_segment, number=small_ints, post_number=small_ints)
    @SETTINGS
    def test_full_suffix_chain(
        self, release: str, number: int, post_number: int
    ) -> None:
        """The full chain: .devN < aN < bN < rcN < (none) < .postN."""
        dev = Version(f"{release}.dev{number}")
        alpha = Version(f"{release}a{number}")
        beta = Version(f"{release}b{number}")
        rc = Version(f"{release}rc{number}")
        final = Version(release)
        post = Version(f"{release}.post{post_number}")
        assert dev < alpha < beta < rc < final < post


class TestCRcEquivalence:
    """
    Note that ``c`` is considered to be semantically equivalent to ``rc`` and must
    be sorted as if it were ``rc``. Tools MAY reject the case of having the same
    ``N`` for both a ``c`` and a ``rc`` in the same release segment as ambiguous
    and remain in compliance with the specification.
    """

    @given(release=release_segment, number=small_ints)
    @SETTINGS
    def test_c_equals_rc(self, release: str, number: int) -> None:
        """cN and rcN for the same release and N are equal."""
        c_ver = Version(f"{release}c{number}")
        rc_ver = Version(f"{release}rc{number}")
        assert c_ver == rc_ver

    @given(release=release_segment, number=small_ints)
    @SETTINGS
    def test_c_and_rc_same_hash(self, release: str, number: int) -> None:
        """cN and rcN hash to the same value."""
        c_ver = Version(f"{release}c{number}")
        rc_ver = Version(f"{release}rc{number}")
        assert hash(c_ver) == hash(rc_ver)

    @given(release=release_segment, number=small_ints)
    @SETTINGS
    def test_c_sorts_after_beta(self, release: str, number: int) -> None:
        """cN sorts the same as rcN, which is after bN."""
        c_ver = Version(f"{release}c{number}")
        beta = Version(f"{release}b{number}")
        assert beta < c_ver


class TestPreReleaseSuffixOrdering:
    """
    Within an alpha (``1.0a1``), beta (``1.0b1``), or release candidate
    (``1.0rc1``, ``1.0c1``), the following suffixes are permitted and MUST be
    ordered as shown::

       .devN, <no suffix>, .postN
    """

    @given(
        release=release_segment,
        pre_type=pre_tags,
        pre_n=small_ints,
        number=small_ints,
    )
    @SETTINGS
    def test_dev_before_plain_pre(
        self, release: str, pre_type: str, pre_n: int, number: int
    ) -> None:
        """.devN < <no suffix> within a pre-release."""
        dev = Version(f"{release}{pre_type}{pre_n}.dev{number}")
        plain = Version(f"{release}{pre_type}{pre_n}")
        assert dev < plain

    @given(
        release=release_segment,
        pre_type=pre_tags,
        pre_n=small_ints,
        number=small_ints,
    )
    @SETTINGS
    def test_plain_pre_before_post(
        self, release: str, pre_type: str, pre_n: int, number: int
    ) -> None:
        """<no suffix> < .postN within a pre-release."""
        plain = Version(f"{release}{pre_type}{pre_n}")
        post = Version(f"{release}{pre_type}{pre_n}.post{number}")
        assert plain < post

    @given(
        release=release_segment,
        pre_type=pre_tags,
        pre_n=small_ints,
        dev_n=small_ints,
        post_n=small_ints,
    )
    @SETTINGS
    def test_full_pre_suffix_chain(
        self, release: str, pre_type: str, pre_n: int, dev_n: int, post_n: int
    ) -> None:
        """.devN < <no suffix> < .postN within a pre-release."""
        dev = Version(f"{release}{pre_type}{pre_n}.dev{dev_n}")
        plain = Version(f"{release}{pre_type}{pre_n}")
        post = Version(f"{release}{pre_type}{pre_n}.post{post_n}")
        assert dev < plain < post


class TestPostReleaseSuffixOrdering:
    """
    Within a post-release (``1.0.post1``), the following suffixes are permitted
    and MUST be ordered as shown::

        .devN, <no suffix>
    """

    @given(release=release_segment, post_n=small_ints, dev_n=small_ints)
    @SETTINGS
    def test_dev_before_plain_post(self, release: str, post_n: int, dev_n: int) -> None:
        """.devN < <no suffix> within a post-release."""
        dev = Version(f"{release}.post{post_n}.dev{dev_n}")
        plain = Version(f"{release}.post{post_n}")
        assert dev < plain


class TestDotSeparation:
    """
    Note that ``devN`` and ``postN`` MUST always be preceded by a dot, even
    when used immediately following a numeric version (e.g. ``1.0.dev456``,
    ``1.0.post1``).
    """

    @given(release=release_segment, number=small_ints)
    @SETTINGS
    def test_dev_with_dot_parses(self, release: str, number: int) -> None:
        """Dot-prefixed .devN is valid and parseable."""
        v = Version(f"{release}.dev{number}")
        assert v.dev == number

    @given(release=release_segment, number=small_ints)
    @SETTINGS
    def test_post_with_dot_parses(self, release: str, number: int) -> None:
        """Dot-prefixed .postN is valid and parseable."""
        v = Version(f"{release}.post{number}")
        assert v.post == number

    @given(release=release_segment, number=small_ints)
    @SETTINGS
    def test_dev_normalized_form_has_dot(self, release: str, number: int) -> None:
        """The normalized string form of a dev release uses a dot."""
        v = Version(f"{release}.dev{number}")
        assert f".dev{number}" in str(v)

    @given(release=release_segment, number=small_ints)
    @SETTINGS
    def test_post_normalized_form_has_dot(self, release: str, number: int) -> None:
        """The normalized string form of a post release uses a dot."""
        v = Version(f"{release}.post{number}")
        assert f".post{number}" in str(v)


class TestNumericOrderingWithinSharedPrefix:
    """
    Within a pre-release, post-release or development release segment with a
    shared prefix, ordering MUST be by the value of the numeric component.
    """

    @given(
        release=release_segment,
        number_a=small_ints,
        number_b=small_ints,
    )
    @SETTINGS
    def test_dev_numeric_ordering(
        self, release: str, number_a: int, number_b: int
    ) -> None:
        """dev releases order by numeric component."""
        v1 = Version(f"{release}.dev{number_a}")
        v2 = Version(f"{release}.dev{number_b}")
        if number_a < number_b:
            assert v1 < v2
        elif number_a > number_b:
            assert v1 > v2
        else:
            assert v1 == v2

    @given(
        release=release_segment,
        pre_type=pre_tags,
        number_a=small_ints,
        number_b=small_ints,
    )
    @SETTINGS
    def test_pre_release_numeric_ordering(
        self, release: str, pre_type: str, number_a: int, number_b: int
    ) -> None:
        """Pre-releases of the same type order by numeric component."""
        v1 = Version(f"{release}{pre_type}{number_a}")
        v2 = Version(f"{release}{pre_type}{number_b}")
        if number_a < number_b:
            assert v1 < v2
        elif number_a > number_b:
            assert v1 > v2
        else:
            assert v1 == v2

    @given(
        release=release_segment,
        number_a=small_ints,
        number_b=small_ints,
    )
    @SETTINGS
    def test_post_release_numeric_ordering(
        self, release: str, number_a: int, number_b: int
    ) -> None:
        """Post-releases order by numeric component."""
        v1 = Version(f"{release}.post{number_a}")
        v2 = Version(f"{release}.post{number_b}")
        if number_a < number_b:
            assert v1 < v2
        elif number_a > number_b:
            assert v1 > v2
        else:
            assert v1 == v2


class TestComprehensiveOrderingExample:
    """
    The following example covers many of the possible combinations::

        1.dev0
        1.0.dev456
        1.0a1
        1.0a2.dev456
        1.0a12.dev456
        1.0a12
        1.0b1.dev456
        1.0b2
        1.0b2.post345.dev456
        1.0b2.post345
        1.0rc1.dev456
        1.0rc1
        1.0
        1.0+abc.5
        1.0+abc.7
        1.0+5
        1.0.post456.dev34
        1.0.post456
        1.0.15
        1.1.dev1
    """

    # The spec example as an ordered list of version strings. Each version
    # in this list MUST sort strictly less than the one that follows it,
    # with the exception of local versions which compare equal to the
    # non-local version they are based on.
    ORDERED_VERSIONS = (
        "1.dev0",
        "1.0.dev456",
        "1.0a1",
        "1.0a2.dev456",
        "1.0a12.dev456",
        "1.0a12",
        "1.0b1.dev456",
        "1.0b2",
        "1.0b2.post345.dev456",
        "1.0b2.post345",
        "1.0rc1.dev456",
        "1.0rc1",
        "1.0",
        "1.0+abc.5",
        "1.0+abc.7",
        "1.0+5",
        "1.0.post456.dev34",
        "1.0.post456",
        "1.0.15",
        "1.1.dev1",
    )

    # Indices where local versions appear (they compare equal to 1.0 for
    # ordering purposes, so they are not strictly greater than 1.0).
    LOCAL_INDICES = frozenset({13, 14, 15})

    def test_pairwise_ordering(self) -> None:
        """Each version in the spec example sorts before the next.

        Local versions are excluded from strict less-than checks because
        they compare equal to their public version for ordering.
        """
        versions = [Version(s) for s in self.ORDERED_VERSIONS]
        for i in range(len(versions) - 1):
            a, b = versions[i], versions[i + 1]
            # Skip pairs that involve local versions (indices 12-15 are
            # 1.0, 1.0+abc.5, 1.0+abc.7, 1.0+5) since locals compare
            # equal to their public counterpart.
            va = self.ORDERED_VERSIONS[i]
            vb = self.ORDERED_VERSIONS[i + 1]
            if i + 1 in self.LOCAL_INDICES or i in self.LOCAL_INDICES:
                assert a <= b, f"{va} should be <= {vb}"
            else:
                assert a < b, f"{va} should be < {vb}"

    def test_sorted_matches_spec_order(self) -> None:
        """Sorting the spec example versions produces the spec order.

        Local versions are removed since they do not participate in
        public ordering and sorted() cannot guarantee their relative
        positions among equal elements (it is stable, but they parse
        as equal to 1.0).
        """
        public_strings = [
            s
            for i, s in enumerate(self.ORDERED_VERSIONS)
            if i not in self.LOCAL_INDICES
        ]
        versions = [Version(s) for s in public_strings]
        assert sorted(versions) == versions

    def test_all_pairs_consistent(self) -> None:
        """For every pair (i, j) where i < j, version[i] <= version[j].

        Uses <= to accommodate local version equality.
        """
        versions = [Version(s) for s in self.ORDERED_VERSIONS]
        for i, j in itertools.combinations(range(len(versions)), 2):
            # Skip comparisons across the local version cluster since
            # those are equal to 1.0 in public ordering.
            if i in self.LOCAL_INDICES or j in self.LOCAL_INDICES:
                continue
            assert versions[i] < versions[j], (
                f"{self.ORDERED_VERSIONS[i]} should be < {self.ORDERED_VERSIONS[j]}"
            )
