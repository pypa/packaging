# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.

from __future__ import annotations

import re

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

from packaging.version import InvalidVersion, Version
from tests.property.strategies import SETTINGS, VERSION_POOL, pre_tags

pytestmark = pytest.mark.property

versions = st.sampled_from(VERSION_POOL)


@st.composite
def generated_versions(draw: st.DrawFn) -> Version:
    """Generate a random valid PEP 440 version from parts."""
    epoch = draw(st.integers(min_value=0, max_value=3))
    num_release = draw(st.integers(min_value=1, max_value=5))
    release = tuple(
        draw(st.integers(min_value=0, max_value=99)) for _ in range(num_release)
    )

    has_pre = draw(st.booleans())
    pre = None
    if has_pre:
        pre_letter = draw(pre_tags)
        pre_num = draw(st.integers(min_value=0, max_value=10))
        pre = (pre_letter, pre_num)

    has_post = draw(st.booleans())
    post = draw(st.integers(min_value=0, max_value=10)) if has_post else None

    has_dev = draw(st.booleans())
    dev = draw(st.integers(min_value=0, max_value=10)) if has_dev else None

    has_local = draw(st.booleans())
    local = None
    if has_local:
        num_segs = draw(st.integers(min_value=1, max_value=3))
        segs = []
        for _ in range(num_segs):
            if draw(st.booleans()):
                segs.append(str(draw(st.integers(min_value=0, max_value=99))))
            else:
                segs.append(
                    draw(
                        st.text(
                            alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz"),
                            min_size=1,
                            max_size=4,
                        )
                    )
                )
        local = ".".join(segs)

    return Version.from_parts(
        epoch=epoch, release=release, pre=pre, post=post, dev=dev, local=local
    )


# to test whitespace stripping behavior.
@st.composite
def version_with_whitespace(draw: st.DrawFn) -> str:
    """Generate a version string potentially wrapped in whitespace."""
    v = draw(versions)
    leading = draw(st.sampled_from(["", " ", "  ", "\t"]))
    trailing = draw(st.sampled_from(["", " ", "  ", "\t"]))
    return leading + str(v) + trailing


class TestPublicVersionScheme:
    """The canonical public version identifiers MUST comply with the following
    scheme::

        [N!]N(.N)*[{a|b|rc}N][.postN][.devN]"""

    @given(version=generated_versions())
    @SETTINGS
    def test_canonical_format_matches_scheme(self, version: Version) -> None:
        """Every generated version, when stringified, matches the canonical
        pattern [N!]N(.N)*[{a|b|rc}N][.postN][.devN] (plus optional local)."""
        s = str(version)
        public = s.split("+", maxsplit=1)[0]
        # This regex matches the canonical public version format
        pattern = re.compile(
            r"^(?:(?P<epoch>[0-9]+)!)?"
            r"(?P<release>[0-9]+(?:\.[0-9]+)*)"
            r"(?:(?P<pre>(?:a|b|rc)[0-9]+))?"
            r"(?:\.post(?P<post>[0-9]+))?"
            r"(?:\.dev(?P<dev>[0-9]+))?$"
        )
        assert pattern.match(public), f"{public!r} does not match canonical format"

    @given(version=generated_versions())
    @SETTINGS
    def test_str_round_trip_is_canonical(self, version: Version) -> None:
        """The string representation of a parsed version is already canonical,
        so parsing it again yields the same string."""
        assert str(Version(str(version))) == str(version)


class TestPublicVersionNoWhitespace:
    """Public version identifiers MUST NOT include leading or trailing whitespace."""

    @given(vs=version_with_whitespace())
    @SETTINGS
    def test_whitespace_stripped_on_parse(self, vs: str) -> None:
        """Leading/trailing whitespace is stripped during parsing. The
        resulting normalized string has no whitespace."""
        v = Version(vs)
        s = str(v)
        assert s == s.strip()
        assert not s.startswith(" ")
        assert not s.endswith(" ")


class TestPublicVersionUniqueness:
    """Public version identifiers MUST be unique within a given distribution."""

    def test_no_properties(self) -> None:
        # Advisory/definitional text about distribution-level uniqueness,
        # no testable properties at the version object level.
        pass


class TestNonCompliantVersionHandling:
    """Installation tools SHOULD ignore any public versions which do not comply with
    this scheme but MUST also include the normalizations specified below.
    Installation tools MAY warn the user when non-compliant or ambiguous versions
    are detected."""

    @given(
        garbage=st.text(
            alphabet=st.sampled_from("!@#$%^&()={}[]|\\:;<>,?/~`"),
            min_size=1,
            max_size=10,
        )
    )
    @SETTINGS
    def test_non_compliant_strings_raise(self, garbage: str) -> None:
        """Strings that are clearly not PEP 440 versions raise InvalidVersion."""
        with pytest.raises(InvalidVersion):
            Version(garbage)


class TestVersionRegexReference:
    """See also :ref:`version-specifiers-regex` which provides a regular
    expression to check strict conformance with the canonical format, as
    well as a more permissive regular expression accepting inputs that may
    require subsequent normalization."""

    def test_no_properties(self) -> None:
        # Reference text, no testable properties.
        pass


class TestVersionSegments:
    """Public version identifiers are separated into up to five segments:

    * Epoch segment: ``N!``
    * Release segment: ``N(.N)*``
    * Pre-release segment: ``{a|b|rc}N``
    * Post-release segment: ``.postN``
    * Development release segment: ``.devN``"""

    @given(version=generated_versions())
    @SETTINGS
    def test_epoch_is_nonnegative_int(self, version: Version) -> None:
        """The epoch segment is a non-negative integer."""
        assert isinstance(version.epoch, int)
        assert version.epoch >= 0

    @given(version=generated_versions())
    @SETTINGS
    def test_release_is_tuple_of_nonneg_ints(self, version: Version) -> None:
        """The release segment is a non-empty tuple of non-negative integers."""
        assert isinstance(version.release, tuple)
        assert len(version.release) >= 1
        for component in version.release:
            assert isinstance(component, int)
            assert component >= 0

    @given(version=generated_versions())
    @SETTINGS
    def test_pre_format(self, version: Version) -> None:
        """If present, pre is a tuple (letter, number) where letter is
        a, b, or rc and number is a non-negative int."""
        if version.pre is not None:
            letter, number = version.pre
            assert letter in ("a", "b", "rc")
            assert isinstance(number, int)
            assert number >= 0

    @given(version=generated_versions())
    @SETTINGS
    def test_post_format(self, version: Version) -> None:
        """If present, post is a non-negative integer."""
        if version.post is not None:
            assert isinstance(version.post, int)
            assert version.post >= 0

    @given(version=generated_versions())
    @SETTINGS
    def test_dev_format(self, version: Version) -> None:
        """If present, dev is a non-negative integer."""
        if version.dev is not None:
            assert isinstance(version.dev, int)
            assert version.dev >= 0


class TestReleaseKinds:
    """Any given release will be a "final release", "pre-release", "post-release" or
    "developmental release" as defined in the following sections."""

    @given(version=generated_versions())
    @SETTINGS
    def test_release_kind_categories(self, version: Version) -> None:
        """Every version falls into at least one of the recognized release
        kinds: final, pre-release, post-release, or developmental release."""
        is_final = version.pre is None and version.post is None and version.dev is None
        is_pre = version.is_prerelease
        is_post = version.is_postrelease
        is_dev = version.is_devrelease
        # At least one category must apply
        assert is_final or is_pre or is_post or is_dev


class TestNumericComponentsNonNegative:
    """All numeric components MUST be non-negative integers represented as sequences
    of ASCII digits."""

    @given(version=generated_versions())
    @SETTINGS
    def test_all_numeric_components_nonneg(self, version: Version) -> None:
        """Every numeric component of a version is a non-negative integer."""
        assert version.epoch >= 0
        for r in version.release:
            assert r >= 0
        if version.pre is not None:
            assert version.pre[1] >= 0
        if version.post is not None:
            assert version.post >= 0
        if version.dev is not None:
            assert version.dev >= 0

    @given(version=generated_versions())
    @SETTINGS
    def test_stringified_numerics_are_ascii_digits(self, version: Version) -> None:
        """When stringified, all numeric parts are pure ASCII digit sequences."""
        s = str(version)
        # Extract all numeric runs from the version string
        for num in re.findall(r"[0-9]+", s):
            assert num.isascii()
            assert num.isdigit()


class TestNumericComponentOrdering:
    """All numeric components MUST be interpreted and ordered according to their
    numeric value, not as text strings."""

    @given(
        number_a=st.integers(min_value=0, max_value=200),
        number_b=st.integers(min_value=0, max_value=200),
    )
    @SETTINGS
    def test_release_numeric_ordering(self, number_a: int, number_b: int) -> None:
        """Release segment components are compared numerically: 9 < 10,
        not lexicographically where "9" > "10"."""
        va = Version(f"{number_a}.0")
        vb = Version(f"{number_b}.0")
        if number_a < number_b:
            assert va < vb
        elif number_a == number_b:
            assert va == vb
        else:
            assert va > vb

    @given(
        number_a=st.integers(min_value=0, max_value=200),
        number_b=st.integers(min_value=0, max_value=200),
    )
    @SETTINGS
    def test_epoch_numeric_ordering(self, number_a: int, number_b: int) -> None:
        """Epoch components are compared numerically."""
        va = Version(f"{number_a}!1.0")
        vb = Version(f"{number_b}!1.0")
        if number_a < number_b:
            assert va < vb
        elif number_a == number_b:
            assert va == vb
        else:
            assert va > vb

    @given(
        number_a=st.integers(min_value=0, max_value=50),
        number_b=st.integers(min_value=0, max_value=50),
    )
    @SETTINGS
    def test_post_numeric_ordering(self, number_a: int, number_b: int) -> None:
        """Post-release numbers are compared numerically."""
        va = Version(f"1.0.post{number_a}")
        vb = Version(f"1.0.post{number_b}")
        if number_a < number_b:
            assert va < vb
        elif number_a == number_b:
            assert va == vb
        else:
            assert va > vb

    @given(
        number_a=st.integers(min_value=0, max_value=50),
        number_b=st.integers(min_value=0, max_value=50),
    )
    @SETTINGS
    def test_dev_numeric_ordering(self, number_a: int, number_b: int) -> None:
        """Dev-release numbers are compared numerically."""
        va = Version(f"1.0.dev{number_a}")
        vb = Version(f"1.0.dev{number_b}")
        if number_a < number_b:
            assert va < vb
        elif number_a == number_b:
            assert va == vb
        else:
            assert va > vb

    @given(
        number_a=st.integers(min_value=0, max_value=50),
        number_b=st.integers(min_value=0, max_value=50),
    )
    @SETTINGS
    def test_pre_numeric_ordering(self, number_a: int, number_b: int) -> None:
        """Pre-release numbers within the same kind are compared numerically."""
        va = Version(f"1.0a{number_a}")
        vb = Version(f"1.0a{number_b}")
        if number_a < number_b:
            assert va < vb
        elif number_a == number_b:
            assert va == vb
        else:
            assert va > vb


class TestNumericComponentZero:
    """All numeric components MAY be zero. Except as described below for the
    release segment, a numeric component of zero has no special significance
    aside from always being the lowest possible value in the version ordering."""

    @given(
        number=st.integers(min_value=1, max_value=50),
    )
    @SETTINGS
    def test_zero_is_lowest_pre(self, number: int) -> None:
        """a0 is the lowest alpha pre-release."""
        assert Version("1.0a0") <= Version(f"1.0a{number}")

    @given(
        number=st.integers(min_value=1, max_value=50),
    )
    @SETTINGS
    def test_zero_is_lowest_post(self, number: int) -> None:
        """post0 is the lowest post-release."""
        assert Version("1.0.post0") <= Version(f"1.0.post{number}")

    @given(
        number=st.integers(min_value=1, max_value=50),
    )
    @SETTINGS
    def test_zero_is_lowest_dev(self, number: int) -> None:
        """dev0 is the lowest dev-release."""
        assert Version("1.0.dev0") <= Version(f"1.0.dev{number}")

    @given(
        number=st.integers(min_value=1, max_value=50),
    )
    @SETTINGS
    def test_zero_is_lowest_epoch(self, number: int) -> None:
        """Epoch 0 is the lowest epoch value."""
        assert Version("0!1.0") <= Version(f"{number}!1.0")

    def test_zero_components_are_valid(self) -> None:
        """All segments accept zero values without error."""
        v = Version("0!0.0.0a0.post0.dev0")
        assert v.epoch == 0
        assert v.release == (0, 0, 0)
        assert v.pre == ("a", 0)
        assert v.post == 0
        assert v.dev == 0


class TestVersioningPracticesNote:
    """.. note::

    Some hard to read version identifiers are permitted by this scheme in
    order to better accommodate the wide range of versioning practices
    across existing public and private Python projects.

    Accordingly, some of the versioning practices which are technically
    permitted by the specification are strongly discouraged for new projects. Where
    this is the case, the relevant details are noted in the following
    sections."""

    def test_no_properties(self) -> None:
        # Advisory note about versioning practices, no testable properties.
        pass


class TestLocalVersionScheme:
    """Local version identifiers MUST comply with the following scheme::

        <public version identifier>[+<local version label>]

    They consist of a normal public version identifier (as defined in the
    previous section), along with an arbitrary "local version label", separated
    from the public version identifier by a plus. Local version labels have
    no specific semantics assigned, but some syntactic restrictions are imposed."""

    @given(version=generated_versions())
    @SETTINGS
    def test_local_separated_by_plus(self, version: Version) -> None:
        """If a version has a local segment, its string representation
        contains exactly one '+' separating public and local parts."""
        s = str(version)
        if version.local is not None:
            assert "+" in s
            parts = s.split("+", 1)
            assert len(parts) == 2
            assert parts[1] == version.local
        else:
            assert "+" not in s

    @given(version=generated_versions())
    @SETTINGS
    def test_public_property_strips_local(self, version: Version) -> None:
        """The .public property returns the version without the local label."""
        public = version.public
        assert "+" not in public
        if version.local is not None:
            assert str(version).startswith(public + "+")
        else:
            assert public == str(version)


class TestLocalVersionPurpose:
    """Local version identifiers are used to denote fully API (and, if applicable,
    ABI) compatible patched versions of upstream projects. For example, these
    may be created by application developers and system integrators by applying
    specific backported bug fixes when upgrading to a new upstream release would
    be too disruptive to the application or other integrated system (such as a
    Linux distribution)."""

    def test_no_properties(self) -> None:
        # Advisory/definitional text about the purpose of local versions,
        # no testable properties.
        pass


class TestLocalVersionDifferentiation:
    """The inclusion of the local version label makes it possible to differentiate
    upstream releases from potentially altered rebuilds by downstream
    integrators. The use of a local version identifier does not affect the kind
    of a release but, when applied to a source distribution, does indicate that
    it may not contain the exact same code as the corresponding upstream release."""

    @given(version=generated_versions())
    @SETTINGS
    def test_local_does_not_affect_release_kind(self, version: Version) -> None:
        """Adding a local label does not change is_prerelease, is_postrelease,
        or is_devrelease."""
        assume(version.local is None)
        v_with_local = Version(str(version) + "+local1")
        assert version.is_prerelease == v_with_local.is_prerelease
        assert version.is_postrelease == v_with_local.is_postrelease
        assert version.is_devrelease == v_with_local.is_devrelease


class TestLocalVersionPermittedCharacters:
    """To ensure local version identifiers can be readily incorporated as part of
    filenames and URLs, and to avoid formatting inconsistencies in hexadecimal
    hash representations, local version labels MUST be limited to the following
    set of permitted characters:

    * ASCII letters (``[a-zA-Z]``)
    * ASCII digits (``[0-9]``)
    * periods (``.``)"""

    @given(version=generated_versions())
    @SETTINGS
    def test_local_label_characters(self, version: Version) -> None:
        """The normalized local label contains only ASCII letters, digits,
        and periods."""
        if version.local is not None:
            for ch in version.local:
                assert ch in "abcdefghijklmnopqrstuvwxyz0123456789.", (
                    f"Unexpected character {ch!r} in local label {version.local!r}"
                )

    @given(
        bad_local=st.text(
            alphabet=st.sampled_from("!@#$%^&*()={}[]|\\:;<>,?/~` "),
            min_size=1,
            max_size=5,
        )
    )
    @SETTINGS
    def test_invalid_local_characters_rejected(self, bad_local: str) -> None:
        """Versions with local labels containing forbidden characters
        are rejected."""
        with pytest.raises(InvalidVersion):
            Version(f"1.0+{bad_local}")


class TestLocalVersionStartEnd:
    """Local version labels MUST start and end with an ASCII letter or digit."""

    def test_local_cannot_start_with_period(self) -> None:
        """A local label starting with a period is rejected."""
        with pytest.raises(InvalidVersion):
            Version("1.0+.abc")

    def test_local_cannot_end_with_period(self) -> None:
        """A local label ending with a period is rejected."""
        with pytest.raises(InvalidVersion):
            Version("1.0+abc.")

    @given(version=generated_versions())
    @SETTINGS
    def test_normalized_local_starts_ends_alnum(self, version: Version) -> None:
        """The normalized local label always starts and ends with an
        alphanumeric character."""
        if version.local is not None:
            assert version.local[0].isalnum()
            assert version.local[-1].isalnum()


class TestLocalVersionComparison:
    """Comparison and ordering of local versions considers each segment of the local
    version (divided by a ``.``) separately. If a segment consists entirely of
    ASCII digits then that section should be considered an integer for comparison
    purposes and if a segment contains any ASCII letters then that segment is
    compared lexicographically with case insensitivity. When comparing a numeric
    and lexicographic segment, the numeric section always compares as greater than
    the lexicographic segment. Additionally a local version with a greater number of
    segments will always compare as greater than a local version with fewer
    segments, as long as the shorter local version's segments match the beginning
    of the longer local version's segments exactly."""

    @given(
        number_a=st.integers(min_value=0, max_value=200),
        number_b=st.integers(min_value=0, max_value=200),
    )
    @SETTINGS
    def test_numeric_segments_compared_as_integers(
        self, number_a: int, number_b: int
    ) -> None:
        """Purely numeric local segments are compared as integers, not strings."""
        va = Version(f"1.0+{number_a}")
        vb = Version(f"1.0+{number_b}")
        if number_a < number_b:
            assert va < vb
        elif number_a == number_b:
            assert va == vb
        else:
            assert va > vb

    @given(
        label=st.text(
            alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz"),
            min_size=1,
            max_size=6,
        )
    )
    @SETTINGS
    def test_alpha_segments_case_insensitive(self, label: str) -> None:
        """Local version segments with letters compare case-insensitively."""
        lower = Version(f"1.0+{label.lower()}")
        upper = Version(f"1.0+{label.upper()}")
        assert lower == upper

    @given(
        number=st.integers(min_value=0, max_value=100),
        label=st.text(
            alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz"),
            min_size=1,
            max_size=6,
        ),
    )
    @SETTINGS
    def test_numeric_greater_than_lexicographic(self, number: int, label: str) -> None:
        """A numeric local segment always compares greater than a
        lexicographic segment."""
        v_num = Version(f"1.0+{number}")
        v_str = Version(f"1.0+{label}")
        assert v_num > v_str

    @given(
        seg=st.text(
            alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz0123456789"),
            min_size=1,
            max_size=4,
        ),
        extra=st.text(
            alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz0123456789"),
            min_size=1,
            max_size=4,
        ),
    )
    @SETTINGS
    def test_longer_local_greater_when_prefix_matches(
        self, seg: str, extra: str
    ) -> None:
        """A local version with more segments compares greater when the
        shorter one's segments match the beginning of the longer exactly."""
        v_short = Version(f"1.0+{seg}")
        v_long = Version(f"1.0+{seg}.{extra}")
        assert v_long > v_short

    @given(
        label_a=st.text(
            alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz"),
            min_size=1,
            max_size=5,
        ),
        label_b=st.text(
            alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz"),
            min_size=1,
            max_size=5,
        ),
    )
    @SETTINGS
    def test_alpha_segments_lexicographic_order(
        self, label_a: str, label_b: str
    ) -> None:
        """Purely alphabetic local segments compare lexicographically
        (case insensitive)."""
        va = Version(f"1.0+{label_a}")
        vb = Version(f"1.0+{label_b}")
        a_low = label_a.lower()
        b_low = label_b.lower()
        if a_low < b_low:
            assert va < vb
        elif a_low == b_low:
            assert va == vb
        else:
            assert va > vb


class TestUpstreamDownstreamDefinition:
    """An "upstream project" is a project that defines its own public versions. A
    "downstream project" is one which tracks and redistributes an upstream project,
    potentially backporting security and bug fixes from later versions of the
    upstream project."""

    def test_no_properties(self) -> None:
        # Definitional text, no testable properties.
        pass


class TestLocalVersionPublishingGuidance:
    """Local version identifiers SHOULD NOT be used when publishing upstream
    projects to a public index server, but MAY be used to identify private
    builds created directly from the project source. Local
    version identifiers SHOULD be used by downstream projects when releasing a
    version that is API compatible with the version of the upstream project
    identified by the public version identifier, but contains additional changes
    (such as bug fixes). As the Python Package Index is intended solely for
    indexing and hosting upstream projects, it MUST NOT allow the use of local
    version identifiers."""

    def test_no_properties(self) -> None:
        # Policy/advisory text about publishing, no testable properties
        # at the version object level.
        pass


class TestSourceDistributionMetadata:
    """Source distributions using a local version identifier SHOULD provide the
    ``python.integrator`` extension metadata (as defined in :pep:`459`)."""

    def test_no_properties(self) -> None:
        # Advisory text about source distribution metadata,
        # no testable properties at the version object level.
        pass


class TestLocalVersionDoesNotAffectPublicOrdering:
    """Comparison and ordering of local versions considers each segment of the local
    version (divided by a ``.``) separately. If a segment consists entirely of
    ASCII digits then that section should be considered an integer for comparison
    purposes and if a segment contains any ASCII letters then that segment is
    compared lexicographically with case insensitivity. When comparing a numeric
    and lexicographic segment, the numeric section always compares as greater than
    the lexicographic segment. Additionally a local version with a greater number of
    segments will always compare as greater than a local version with fewer
    segments, as long as the shorter local version's segments match the beginning
    of the longer local version's segments exactly."""

    @given(version=versions)
    @SETTINGS
    def test_version_with_local_greater_than_without(self, version: Version) -> None:
        """A version with a local segment is greater than the same version
        without one (local versions sort after the public version)."""
        assume(version.local is None)
        v_local = Version(str(version) + "+1")
        assert v_local > version

    @given(version=versions)
    @SETTINGS
    def test_two_locals_share_public(self, version: Version) -> None:
        """Two versions differing only in local label share the same
        .public property."""
        assume(version.local is None)
        v1 = Version(str(version) + "+abc")
        v2 = Version(str(version) + "+xyz")
        assert v1.public == v2.public == str(version)
