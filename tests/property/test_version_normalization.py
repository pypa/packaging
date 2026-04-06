# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from packaging.version import InvalidVersion, Version
from tests.property.strategies import (
    SETTINGS,
    pre_tags,
    release_segment,
    small_ints,
)

pytestmark = pytest.mark.property

# Values of varying digit lengths for leading-zero stripping ("007" -> "7").
_ints_for_padding = st.sampled_from([0, 5, 12, 123, 1234, 99999])


@st.composite
def padded_int(draw: st.DrawFn) -> str:
    """An integer with optional leading zeros, e.g. '007'."""
    val = draw(_ints_for_padding)
    padding = draw(st.integers(min_value=0, max_value=4))
    return "0" * padding + str(val)


@st.composite
def padded_release(draw: st.DrawFn) -> tuple[str, str]:
    """A release segment with padded ints, returning (padded, normalized)."""
    count = draw(st.integers(min_value=1, max_value=4))
    padded_parts = []
    normal_parts = []
    for _ in range(count):
        val = draw(_ints_for_padding)
        padding = draw(st.integers(min_value=0, max_value=4))
        padded_parts.append("0" * padding + str(val))
        normal_parts.append(str(val))
    return ".".join(padded_parts), ".".join(normal_parts)


class TestCaseSensitivity:
    """In order to maintain better compatibility with existing versions there are a
    number of "alternative" syntaxes that MUST be taken into account when parsing
    versions. These syntaxes MUST be considered when parsing a version, however
    they should be "normalized" to the standard syntax defined above.

    All ascii letters should be interpreted case insensitively within a version and
    the normal form is lowercase. This allows versions such as ``1.1RC1`` which
    would be normalized to ``1.1rc1``."""

    @given(
        release=release_segment,
        pre_type=pre_tags,
        pre_num=small_ints,
    )
    @SETTINGS
    def test_pre_release_case_insensitive(
        self, release: str, pre_type: str, pre_num: int
    ) -> None:
        """Pre-release letters parse the same regardless of case."""
        lower = f"{release}{pre_type}{pre_num}"
        upper = f"{release}{pre_type.upper()}{pre_num}"
        mixed = f"{release}{pre_type.capitalize()}{pre_num}"
        v_lower = Version(lower)
        assert Version(upper) == v_lower
        assert Version(mixed) == v_lower

    @given(release=release_segment, post_num=small_ints)
    @SETTINGS
    def test_post_release_case_insensitive(self, release: str, post_num: int) -> None:
        """'post' is case insensitive."""
        normal = Version(f"{release}.post{post_num}")
        assert Version(f"{release}.POST{post_num}") == normal
        assert Version(f"{release}.Post{post_num}") == normal

    @given(release=release_segment, dev_num=small_ints)
    @SETTINGS
    def test_dev_release_case_insensitive(self, release: str, dev_num: int) -> None:
        """'dev' is case insensitive."""
        normal = Version(f"{release}.dev{dev_num}")
        assert Version(f"{release}.DEV{dev_num}") == normal
        assert Version(f"{release}.Dev{dev_num}") == normal

    @given(
        release=release_segment,
        pre_type=pre_tags,
        pre_num=small_ints,
    )
    @SETTINGS
    def test_normal_form_is_lowercase(
        self, release: str, pre_type: str, pre_num: int
    ) -> None:
        """The normalized string form uses lowercase."""
        v = Version(f"{release}{pre_type.upper()}{pre_num}")
        assert pre_type in str(v)
        assert pre_type.upper() not in str(v) or pre_type == pre_type.upper()


class TestIntegerNormalization:
    """All integers are interpreted via the ``int()`` built in and normalize to the
    string form of the output. This means that an integer version of ``00`` would
    normalize to ``0`` while ``09000`` would normalize to ``9000``. This does not
    hold true for integers inside of an alphanumeric segment of a local version
    such as ``1.0+foo0100`` which is already in its normalized form."""

    @given(data=padded_release())
    @SETTINGS
    def test_release_integers_normalized(self, data: tuple[str, str]) -> None:
        """Leading zeros in release segments are stripped."""
        padded, normalized = data
        v = Version(padded)
        assert str(v) == normalized

    @given(
        release=release_segment,
        pre_type=pre_tags,
        pre_num=padded_int(),
    )
    @SETTINGS
    def test_pre_release_integer_normalized(
        self, release: str, pre_type: str, pre_num: str
    ) -> None:
        """Leading zeros in pre-release numbers are stripped."""
        v = Version(f"{release}{pre_type}{pre_num}")
        expected_num = str(int(pre_num))
        assert str(v).endswith(f"{pre_type}{expected_num}")

    @given(release=release_segment, post_num=padded_int())
    @SETTINGS
    def test_post_release_integer_normalized(self, release: str, post_num: str) -> None:
        """Leading zeros in post-release numbers are stripped."""
        v = Version(f"{release}.post{post_num}")
        assert f".post{int(post_num)}" in str(v)

    @given(release=release_segment, dev_num=padded_int())
    @SETTINGS
    def test_dev_release_integer_normalized(self, release: str, dev_num: str) -> None:
        """Leading zeros in dev-release numbers are stripped."""
        v = Version(f"{release}.dev{dev_num}")
        assert f".dev{int(dev_num)}" in str(v)

    @given(
        release=release_segment,
        alpha_segment=st.from_regex(r"[a-zA-Z]+[0-9]+", fullmatch=True),
    )
    @SETTINGS
    def test_local_alphanumeric_not_normalized(
        self, release: str, alpha_segment: str
    ) -> None:
        """Integers inside alphanumeric local segments are preserved."""
        version_str = f"{release}+{alpha_segment}"
        v = Version(version_str)
        local_str = str(v).split("+", 1)[1]
        # The local part should preserve the alphanumeric segment as-is
        # (lowercased, but digits unchanged).
        assert local_str == alpha_segment.lower()


class TestPreReleaseSeparators:
    """Pre-releases should allow a ``.``, ``-``, or ``_`` separator between the
    release segment and the pre-release segment. The normal form for this is
    without a separator. This allows versions such as ``1.1.a1`` or ``1.1-a1``
    which would be normalized to ``1.1a1``. It should also allow a separator to
    be used between the pre-release signifier and the numeral. This allows versions
    such as ``1.0a.1`` which would be normalized to ``1.0a1``."""

    @given(
        release=release_segment,
        sep=st.sampled_from([".", "-", "_"]),
        pre_type=pre_tags,
        pre_num=small_ints,
    )
    @SETTINGS
    def test_separator_before_pre_release(
        self, release: str, sep: str, pre_type: str, pre_num: int
    ) -> None:
        """Separators between release and pre-release normalize away."""
        with_sep = Version(f"{release}{sep}{pre_type}{pre_num}")
        without_sep = Version(f"{release}{pre_type}{pre_num}")
        assert with_sep == without_sep
        assert str(with_sep) == str(without_sep)

    @given(
        release=release_segment,
        sep=st.sampled_from([".", "-", "_"]),
        pre_type=pre_tags,
        pre_num=small_ints,
    )
    @SETTINGS
    def test_separator_between_signifier_and_numeral(
        self, release: str, sep: str, pre_type: str, pre_num: int
    ) -> None:
        """Separators between pre-release signifier and number normalize away."""
        with_sep = Version(f"{release}{pre_type}{sep}{pre_num}")
        without_sep = Version(f"{release}{pre_type}{pre_num}")
        assert with_sep == without_sep
        assert str(with_sep) == str(without_sep)

    @given(
        release=release_segment,
        pre_type=pre_tags,
        pre_num=small_ints,
    )
    @SETTINGS
    def test_normal_form_has_no_separator(
        self, release: str, pre_type: str, pre_num: int
    ) -> None:
        """The normalized string has no separator before the pre-release."""
        v = Version(f"{release}.{pre_type}{pre_num}")
        normalized = str(v)
        # The normalized form should directly adjoin release digits and pre type.
        # Verify by reparsing: the str form shouldn't have .<pre_type>.
        assert f".{pre_type}" not in normalized or normalized.count(
            "."
        ) == release.count(".")


class TestPreReleaseSpelling:
    """Pre-releases allow the additional spellings of ``alpha``, ``beta``, ``c``,
    ``pre``, and ``preview`` for ``a``, ``b``, ``rc``, ``rc``, and ``rc``
    respectively. This allows versions such as ``1.1alpha1``, ``1.1beta2``, or
    ``1.1c3`` which normalize to ``1.1a1``, ``1.1b2``, and ``1.1rc3``. In every
    case the additional spelling should be considered equivalent to their normal
    forms."""

    @given(release=release_segment, pre_num=small_ints)
    @SETTINGS
    def test_alpha_spelling(self, release: str, pre_num: int) -> None:
        """'alpha' normalizes to 'a'."""
        assert Version(f"{release}alpha{pre_num}") == Version(f"{release}a{pre_num}")
        assert "a" in str(Version(f"{release}alpha{pre_num}"))

    @given(release=release_segment, pre_num=small_ints)
    @SETTINGS
    def test_beta_spelling(self, release: str, pre_num: int) -> None:
        """'beta' normalizes to 'b'."""
        assert Version(f"{release}beta{pre_num}") == Version(f"{release}b{pre_num}")
        assert "b" in str(Version(f"{release}beta{pre_num}"))

    @given(
        release=release_segment,
        alt=st.sampled_from(["c", "pre", "preview"]),
        pre_num=small_ints,
    )
    @SETTINGS
    def test_rc_spellings(self, release: str, alt: str, pre_num: int) -> None:
        """'c', 'pre', and 'preview' all normalize to 'rc'."""
        assert Version(f"{release}{alt}{pre_num}") == Version(f"{release}rc{pre_num}")
        assert "rc" in str(Version(f"{release}{alt}{pre_num}"))

    @given(
        release=release_segment,
        spelling=st.sampled_from(
            [
                ("alpha", "a"),
                ("beta", "b"),
                ("c", "rc"),
                ("pre", "rc"),
                ("preview", "rc"),
            ]
        ),
        pre_num=small_ints,
    )
    @SETTINGS
    def test_normalized_form_uses_short_spelling(
        self, release: str, spelling: tuple[str, str], pre_num: int
    ) -> None:
        """The str() output always uses the short form."""
        alt, short = spelling
        v = Version(f"{release}{alt}{pre_num}")
        normalized = str(v)
        assert short in normalized
        # The long spelling should not appear in the output. For 'c' -> 'rc',
        # 'c' is a substring of 'rc' so we check that the pre-release tag is
        # exactly 'rc', not just 'c'.
        if alt in ("alpha", "beta", "preview"):
            assert alt not in normalized
        elif alt == "pre":
            # 'pre' should not appear outside of being part of another word
            assert "pre" not in normalized.split("rc", maxsplit=1)[0]


class TestImplicitPreReleaseNumber:
    """Pre releases allow omitting the numeral in which case it is implicitly assumed
    to be ``0``. The normal form for this is to include the ``0`` explicitly. This
    allows versions such as ``1.2a`` which is normalized to ``1.2a0``."""

    @given(
        release=release_segment,
        pre_type=pre_tags,
    )
    @SETTINGS
    def test_omitted_numeral_equals_zero(self, release: str, pre_type: str) -> None:
        """Omitting the pre-release number is the same as 0."""
        assert Version(f"{release}{pre_type}") == Version(f"{release}{pre_type}0")

    @given(
        release=release_segment,
        pre_type=pre_tags,
    )
    @SETTINGS
    def test_normalized_form_includes_zero(self, release: str, pre_type: str) -> None:
        """The normalized string explicitly includes 0."""
        v = Version(f"{release}{pre_type}")
        assert str(v).endswith(f"{pre_type}0")


class TestPostReleaseSeparators:
    """Post releases allow a ``.``, ``-``, or ``_`` separator as well as omitting the
    separator all together. The normal form of this is with the ``.`` separator.
    This allows versions such as ``1.2-post2`` or ``1.2post2`` which normalize to
    ``1.2.post2``. Like the pre-release separator this also allows an optional
    separator between the post release signifier and the numeral. This allows
    versions like ``1.2.post-2`` which would normalize to ``1.2.post2``."""

    @given(
        release=release_segment,
        sep=st.sampled_from([".", "-", "_", ""]),
        post_num=small_ints,
    )
    @SETTINGS
    def test_separator_before_post(self, release: str, sep: str, post_num: int) -> None:
        """All separators (and none) before 'post' normalize to '.'."""
        v = Version(f"{release}{sep}post{post_num}")
        expected = Version(f"{release}.post{post_num}")
        assert v == expected
        assert str(v) == str(expected)

    @given(
        release=release_segment,
        sep=st.sampled_from([".", "-", "_"]),
        post_num=small_ints,
    )
    @SETTINGS
    def test_separator_between_post_and_numeral(
        self, release: str, sep: str, post_num: int
    ) -> None:
        """Separators between 'post' and the number normalize away."""
        v = Version(f"{release}.post{sep}{post_num}")
        expected = Version(f"{release}.post{post_num}")
        assert v == expected
        assert str(v) == str(expected)

    @given(release=release_segment, post_num=small_ints)
    @SETTINGS
    def test_normal_form_uses_dot_separator(self, release: str, post_num: int) -> None:
        """The normalized string uses '.' before 'post'."""
        v = Version(f"{release}-post{post_num}")
        assert f".post{post_num}" in str(v)


class TestPostReleaseSpelling:
    """Post-releases allow the additional spellings of ``rev`` and ``r``. This allows
    versions such as ``1.0-r4`` which normalizes to ``1.0.post4``. As with the
    pre-releases the additional spellings should be considered equivalent to their
    normal forms."""

    @given(
        release=release_segment,
        alt=st.sampled_from(["rev", "r"]),
        post_num=small_ints,
    )
    @SETTINGS
    def test_alt_spellings_equal_post(
        self, release: str, alt: str, post_num: int
    ) -> None:
        """'rev' and 'r' normalize to 'post'."""
        v_alt = Version(f"{release}-{alt}{post_num}")
        v_normal = Version(f"{release}.post{post_num}")
        assert v_alt == v_normal
        assert str(v_alt) == str(v_normal)

    @given(
        release=release_segment,
        alt=st.sampled_from(["rev", "r"]),
        post_num=small_ints,
    )
    @SETTINGS
    def test_normalized_form_uses_post(
        self, release: str, alt: str, post_num: int
    ) -> None:
        """The str() output uses 'post', not the alternative spelling."""
        v = Version(f"{release}-{alt}{post_num}")
        assert ".post" in str(v)
        assert alt not in str(v) or alt == "r"  # 'r' appears in many words


class TestImplicitPostReleaseNumber:
    """Post releases allow omitting the numeral in which case it is implicitly assumed
    to be ``0``. The normal form for this is to include the ``0`` explicitly. This
    allows versions such as ``1.2.post`` which is normalized to ``1.2.post0``."""

    @given(release=release_segment)
    @SETTINGS
    def test_omitted_numeral_equals_zero(self, release: str) -> None:
        """Omitting the post number is the same as post0."""
        assert Version(f"{release}.post") == Version(f"{release}.post0")

    @given(release=release_segment)
    @SETTINGS
    def test_normalized_form_includes_zero(self, release: str) -> None:
        """The normalized string explicitly includes 0."""
        v = Version(f"{release}.post")
        assert str(v).endswith(".post0")


class TestImplicitPostReleases:
    """Post releases allow omitting the ``post`` signifier all together. When using
    this form the separator MUST be ``-`` and no other form is allowed. This allows
    versions such as ``1.0-1`` to be normalized to ``1.0.post1``. This particular
    normalization MUST NOT be used in conjunction with the implicit post release
    number rule. In other words, ``1.0-`` is *not* a valid version and it does *not*
    normalize to ``1.0.post0``."""

    @given(
        release=release_segment,
        post_num=st.integers(min_value=1, max_value=999),
    )
    @SETTINGS
    def test_dash_number_is_implicit_post(self, release: str, post_num: int) -> None:
        """'release-N' normalizes to 'release.postN'."""
        v = Version(f"{release}-{post_num}")
        expected = Version(f"{release}.post{post_num}")
        assert v == expected
        assert str(v) == str(expected)

    @given(release=release_segment)
    @SETTINGS
    def test_dash_without_number_is_invalid(self, release: str) -> None:
        """'release-' is not a valid version."""
        with pytest.raises(InvalidVersion):
            Version(f"{release}-")


class TestDevelopmentReleaseSeparators:
    """Development releases allow a ``.``, ``-``, or a ``_`` separator as well as
    omitting the separator all together. The normal form of this is with the ``.``
    separator. This allows versions such as ``1.2-dev2`` or ``1.2dev2`` which
    normalize to ``1.2.dev2``."""

    @given(
        release=release_segment,
        sep=st.sampled_from([".", "-", "_", ""]),
        dev_num=small_ints,
    )
    @SETTINGS
    def test_all_separators_normalize_to_dot(
        self, release: str, sep: str, dev_num: int
    ) -> None:
        """All separators (and none) before 'dev' normalize to '.'."""
        v = Version(f"{release}{sep}dev{dev_num}")
        expected = Version(f"{release}.dev{dev_num}")
        assert v == expected
        assert str(v) == str(expected)

    @given(release=release_segment, dev_num=small_ints)
    @SETTINGS
    def test_normal_form_uses_dot_separator(self, release: str, dev_num: int) -> None:
        """The normalized string uses '.' before 'dev'."""
        v = Version(f"{release}-dev{dev_num}")
        assert f".dev{dev_num}" in str(v)


class TestImplicitDevelopmentReleaseNumber:
    """Development releases allow omitting the numeral in which case it is implicitly
    assumed to be ``0``. The normal form for this is to include the ``0``
    explicitly. This allows versions such as ``1.2.dev`` which is normalized to
    ``1.2.dev0``."""

    @given(release=release_segment)
    @SETTINGS
    def test_omitted_numeral_equals_zero(self, release: str) -> None:
        """Omitting the dev number is the same as dev0."""
        assert Version(f"{release}.dev") == Version(f"{release}.dev0")

    @given(release=release_segment)
    @SETTINGS
    def test_normalized_form_includes_zero(self, release: str) -> None:
        """The normalized string explicitly includes 0."""
        v = Version(f"{release}.dev")
        assert str(v).endswith(".dev0")


class TestLocalVersionSegments:
    """With a local version, in addition to the use of ``.`` as a separator of
    segments, the use of ``-`` and ``_`` is also acceptable. The normal form is
    using the ``.`` character. This allows versions such as ``1.0+ubuntu-1`` to be
    normalized to ``1.0+ubuntu.1``."""

    @given(
        release=release_segment,
        local_parts=st.lists(
            st.from_regex(r"[a-zA-Z0-9]+", fullmatch=True),
            min_size=1,
            max_size=4,
        ),
        sep=st.sampled_from([".", "-", "_"]),
    )
    @SETTINGS
    def test_local_separators_normalize_to_dot(
        self, release: str, local_parts: list[str], sep: str
    ) -> None:
        """'-' and '_' in local segments normalize to '.'."""
        local = sep.join(local_parts)
        v = Version(f"{release}+{local}")

        def _normalize_local_part(p: str) -> str:
            # Purely numeric local segments are normalized via int().
            if p.isdigit():
                return str(int(p))
            return p.lower()

        expected_local = ".".join(_normalize_local_part(p) for p in local_parts)
        assert str(v).endswith(f"+{expected_local}")

    @given(
        release=release_segment,
        local_parts=st.lists(
            st.from_regex(r"[a-zA-Z0-9]+", fullmatch=True),
            min_size=2,
            max_size=4,
        ),
    )
    @SETTINGS
    def test_mixed_separators_normalize(
        self, release: str, local_parts: list[str]
    ) -> None:
        """Mixed separators all become dots."""
        seps = ["-", "_", "."]
        # Join with alternating separators
        local = local_parts[0]
        for i, part in enumerate(local_parts[1:]):
            local += seps[i % len(seps)] + part
        v = Version(f"{release}+{local}")

        def _normalize_local_part(p: str) -> str:
            if p.isdigit():
                return str(int(p))
            return p.lower()

        expected_local = ".".join(_normalize_local_part(p) for p in local_parts)
        assert str(v).endswith(f"+{expected_local}")


class TestPrecedingVCharacter:
    """In order to support the common version notation of ``v1.0`` versions may be
    preceded by a single literal ``v`` character. This character MUST be ignored
    for all purposes and should be omitted from all normalized forms of the
    version. The same version with and without the ``v`` is considered equivalent."""

    @given(release=release_segment)
    @SETTINGS
    def test_v_prefix_ignored(self, release: str) -> None:
        """'v' prefix is stripped and versions are equal."""
        assert Version(f"v{release}") == Version(release)

    @given(release=release_segment)
    @SETTINGS
    def test_uppercase_v_prefix_ignored(self, release: str) -> None:
        """'V' prefix is also stripped."""
        assert Version(f"V{release}") == Version(release)

    @given(release=release_segment)
    @SETTINGS
    def test_normalized_form_omits_v(self, release: str) -> None:
        """The normalized string does not start with 'v'."""
        v = Version(f"v{release}")
        assert not str(v).startswith("v")
        assert not str(v).startswith("V")

    @given(
        release=release_segment,
        pre_type=pre_tags,
        pre_num=small_ints,
    )
    @SETTINGS
    def test_v_prefix_with_pre_release(
        self, release: str, pre_type: str, pre_num: int
    ) -> None:
        """'v' prefix works with pre-release versions."""
        v_str = f"v{release}{pre_type}{pre_num}"
        normal_str = f"{release}{pre_type}{pre_num}"
        assert Version(v_str) == Version(normal_str)
        assert str(Version(v_str)) == str(Version(normal_str))


class TestLeadingAndTrailingWhitespace:
    r"""Leading and trailing whitespace must be silently ignored and removed from all
    normalized forms of a version. This includes ``" "``, ``\t``, ``\n``, ``\r``,
    ``\f``, and ``\v``. This allows accidental whitespace to be handled sensibly,
    such as a version like ``1.0\n`` which normalizes to ``1.0``."""

    @given(
        release=release_segment,
        leading=st.text(
            alphabet=st.sampled_from([" ", "\t", "\n", "\r", "\f", "\v"]),
            min_size=0,
            max_size=3,
        ),
        trailing=st.text(
            alphabet=st.sampled_from([" ", "\t", "\n", "\r", "\f", "\v"]),
            min_size=0,
            max_size=3,
        ),
    )
    @SETTINGS
    def test_whitespace_stripped(
        self, release: str, leading: str, trailing: str
    ) -> None:
        """Leading and trailing whitespace is ignored."""
        v_padded = Version(f"{leading}{release}{trailing}")
        v_clean = Version(release)
        assert v_padded == v_clean
        assert str(v_padded) == str(v_clean)

    @given(release=release_segment)
    @SETTINGS
    def test_tab_whitespace(self, release: str) -> None:
        r"""Tab characters are stripped."""
        assert Version(f"\t{release}\t") == Version(release)

    @given(release=release_segment)
    @SETTINGS
    def test_newline_whitespace(self, release: str) -> None:
        r"""Newline characters are stripped."""
        assert Version(f"\n{release}\n") == Version(release)

    @given(release=release_segment)
    @SETTINGS
    def test_normalized_form_has_no_whitespace(self, release: str) -> None:
        """The normalized string has no leading or trailing whitespace."""
        v = Version(f"  {release}  ")
        s = str(v)
        assert s == s.strip()
