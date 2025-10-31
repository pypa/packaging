# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.

import itertools
import operator

import pytest

from packaging.specifiers import InvalidSpecifier, Specifier, SpecifierSet
from packaging.version import Version, parse

from .test_version import VERSIONS

LEGACY_SPECIFIERS = [
    "==2.1.0.3",
    "!=2.2.0.5",
    "<=5",
    ">=7.9a1",
    "<1.0.dev1",
    ">2.0.post1",
]

SPECIFIERS = [
    "~=2.0",
    "==2.1.*",
    "==2.1.0.3",
    "!=2.2.*",
    "!=2.2.0.5",
    "<=5",
    ">=7.9a1",
    "<1.0.dev1",
    ">2.0.post1",
]


class TestSpecifier:
    @pytest.mark.parametrize("specifier", SPECIFIERS)
    def test_specifiers_valid(self, specifier):
        Specifier(specifier)

    @pytest.mark.parametrize(
        "specifier",
        [
            # Operator-less specifier
            "2.0",
            # Invalid operator
            "=>2.0",
            # Version-less specifier
            "==",
            # Local segment on operators which don't support them
            "~=1.0+5",
            ">=1.0+deadbeef",
            "<=1.0+abc123",
            ">1.0+watwat",
            "<1.0+1.0",
            # Prefix matching on operators which don't support them
            "~=1.0.*",
            ">=1.0.*",
            "<=1.0.*",
            ">1.0.*",
            "<1.0.*",
            # Combination of local and prefix matching on operators which do
            # support one or the other
            "==1.0.*+5",
            "!=1.0.*+deadbeef",
            # Prefix matching cannot be used with a pre-release, post-release,
            # dev or local version
            "==2.0a1.*",
            "!=2.0a1.*",
            "==2.0.post1.*",
            "!=2.0.post1.*",
            "==2.0.dev1.*",
            "!=2.0.dev1.*",
            "==1.0+5.*",
            "!=1.0+deadbeef.*",
            # Prefix matching must appear at the end
            "==1.0.*.5",
            # Compatible operator requires 2 digits in the release operator
            "~=1",
            # Cannot use a prefix matching after a .devN version
            "==1.0.dev1.*",
            "!=1.0.dev1.*",
        ],
    )
    def test_specifiers_invalid(self, specifier):
        with pytest.raises(InvalidSpecifier):
            Specifier(specifier)

    @pytest.mark.parametrize(
        "version",
        [
            # Various development release incarnations
            "1.0dev",
            "1.0.dev",
            "1.0dev1",
            "1.0-dev",
            "1.0-dev1",
            "1.0DEV",
            "1.0.DEV",
            "1.0DEV1",
            "1.0.DEV1",
            "1.0-DEV",
            "1.0-DEV1",
            # Various alpha incarnations
            "1.0a",
            "1.0.a",
            "1.0.a1",
            "1.0-a",
            "1.0-a1",
            "1.0alpha",
            "1.0.alpha",
            "1.0.alpha1",
            "1.0-alpha",
            "1.0-alpha1",
            "1.0A",
            "1.0.A",
            "1.0.A1",
            "1.0-A",
            "1.0-A1",
            "1.0ALPHA",
            "1.0.ALPHA",
            "1.0.ALPHA1",
            "1.0-ALPHA",
            "1.0-ALPHA1",
            # Various beta incarnations
            "1.0b",
            "1.0.b",
            "1.0.b1",
            "1.0-b",
            "1.0-b1",
            "1.0beta",
            "1.0.beta",
            "1.0.beta1",
            "1.0-beta",
            "1.0-beta1",
            "1.0B",
            "1.0.B",
            "1.0.B1",
            "1.0-B",
            "1.0-B1",
            "1.0BETA",
            "1.0.BETA",
            "1.0.BETA1",
            "1.0-BETA",
            "1.0-BETA1",
            # Various release candidate incarnations
            "1.0c",
            "1.0.c",
            "1.0.c1",
            "1.0-c",
            "1.0-c1",
            "1.0rc",
            "1.0.rc",
            "1.0.rc1",
            "1.0-rc",
            "1.0-rc1",
            "1.0C",
            "1.0.C",
            "1.0.C1",
            "1.0-C",
            "1.0-C1",
            "1.0RC",
            "1.0.RC",
            "1.0.RC1",
            "1.0-RC",
            "1.0-RC1",
            # Various post release incarnations
            "1.0post",
            "1.0.post",
            "1.0post1",
            "1.0-post",
            "1.0-post1",
            "1.0POST",
            "1.0.POST",
            "1.0POST1",
            "1.0.POST1",
            "1.0-POST",
            "1.0-POST1",
            "1.0-5",
            # Local version case insensitivity
            "1.0+AbC",
            # Integer Normalization
            "1.01",
            "1.0a05",
            "1.0b07",
            "1.0c056",
            "1.0rc09",
            "1.0.post000",
            "1.1.dev09000",
            "00!1.2",
            "0100!0.0",
            # Various other normalizations
            "v1.0",
            "  \r \f \v v1.0\t\n",
        ],
    )
    def test_specifiers_normalized(self, version):
        if "+" not in version:
            ops = ["~=", "==", "!=", "<=", ">=", "<", ">"]
        else:
            ops = ["==", "!="]

        for op in ops:
            Specifier(op + version)

    @pytest.mark.parametrize(
        ("specifier", "expected"),
        [
            # Single item specifiers should just be reflexive
            ("!=2.0", "!=2.0"),
            ("<2.0", "<2.0"),
            ("<=2.0", "<=2.0"),
            ("==2.0", "==2.0"),
            (">2.0", ">2.0"),
            (">=2.0", ">=2.0"),
            ("~=2.0", "~=2.0"),
            # Spaces should be removed
            ("< 2", "<2"),
        ],
    )
    def test_specifiers_str_and_repr(self, specifier, expected):
        spec = Specifier(specifier)

        assert str(spec) == expected
        assert repr(spec) == f"<Specifier({expected!r})>"

    @pytest.mark.parametrize("specifier", SPECIFIERS)
    def test_specifiers_hash(self, specifier):
        assert hash(Specifier(specifier)) == hash(Specifier(specifier))

    @pytest.mark.parametrize(
        ("left", "right", "op"),
        itertools.chain.from_iterable(
            # Verify that the equal (==) operator works correctly
            [[(x, x, operator.eq) for x in SPECIFIERS]]
            +
            # Verify that the not equal (!=) operator works correctly
            [
                [(x, y, operator.ne) for j, y in enumerate(SPECIFIERS) if i != j]
                for i, x in enumerate(SPECIFIERS)
            ]
        ),
    )
    def test_comparison_true(self, left, right, op):
        assert op(Specifier(left), Specifier(right))
        assert op(left, Specifier(right))
        assert op(Specifier(left), right)

    @pytest.mark.parametrize(("left", "right"), [("==2.8.0", "==2.8")])
    def test_comparison_canonicalizes(self, left, right):
        assert Specifier(left) == Specifier(right)
        assert left == Specifier(right)
        assert Specifier(left) == right

    @pytest.mark.parametrize(
        ("left", "right", "op"),
        itertools.chain.from_iterable(
            # Verify that the equal (==) operator works correctly
            [[(x, x, operator.ne) for x in SPECIFIERS]]
            +
            # Verify that the not equal (!=) operator works correctly
            [
                [(x, y, operator.eq) for j, y in enumerate(SPECIFIERS) if i != j]
                for i, x in enumerate(SPECIFIERS)
            ]
        ),
    )
    def test_comparison_false(self, left, right, op):
        assert not op(Specifier(left), Specifier(right))
        assert not op(left, Specifier(right))
        assert not op(Specifier(left), right)

    def test_comparison_non_specifier(self):
        assert Specifier("==1.0") != 12
        assert not Specifier("==1.0") == 12
        assert Specifier("==1.0") != "12"
        assert not Specifier("==1.0") == "12"

    @pytest.mark.parametrize(
        ("version", "spec", "expected"),
        [
            (v, s, True)
            for v, s in [
                # Test the equality operation
                ("2.0", "==2"),
                ("2.0", "==2.0"),
                ("2.0", "==2.0.0"),
                ("2.0+deadbeef", "==2"),
                ("2.0+deadbeef", "==2.0"),
                ("2.0+deadbeef", "==2.0.0"),
                ("2.0+deadbeef", "==2+deadbeef"),
                ("2.0+deadbeef", "==2.0+deadbeef"),
                ("2.0+deadbeef", "==2.0.0+deadbeef"),
                ("2.0+deadbeef.0", "==2.0.0+deadbeef.00"),
                # Test the equality operation with a prefix
                ("2.dev1", "==2.*"),
                ("2a1", "==2.*"),
                ("2a1.post1", "==2.*"),
                ("2b1", "==2.*"),
                ("2b1.dev1", "==2.*"),
                ("2c1", "==2.*"),
                ("2c1.post1.dev1", "==2.*"),
                ("2c1.post1.dev1", "==2.0.*"),
                ("2rc1", "==2.*"),
                ("2rc1", "==2.0.*"),
                ("2", "==2.*"),
                ("2", "==2.0.*"),
                ("2", "==0!2.*"),
                ("0!2", "==2.*"),
                ("2.0", "==2.*"),
                ("2.0.0", "==2.*"),
                ("2.1+local.version", "==2.1.*"),
                # Test the in-equality operation
                ("2.1", "!=2"),
                ("2.1", "!=2.0"),
                ("2.0.1", "!=2"),
                ("2.0.1", "!=2.0"),
                ("2.0.1", "!=2.0.0"),
                ("2.0", "!=2.0+deadbeef"),
                # Test the in-equality operation with a prefix
                ("2.0", "!=3.*"),
                ("2.1", "!=2.0.*"),
                # Test the greater than equal operation
                ("2.0", ">=2"),
                ("2.0", ">=2.0"),
                ("2.0", ">=2.0.0"),
                ("2.0.post1", ">=2"),
                ("2.0.post1.dev1", ">=2"),
                ("3", ">=2"),
                ("3.0.0a8", ">=3.0.0a7"),
                # Test the less than equal operation
                ("2.0", "<=2"),
                ("2.0", "<=2.0"),
                ("2.0", "<=2.0.0"),
                ("2.0.dev1", "<=2"),
                ("2.0a1", "<=2"),
                ("2.0a1.dev1", "<=2"),
                ("2.0b1", "<=2"),
                ("2.0b1.post1", "<=2"),
                ("2.0c1", "<=2"),
                ("2.0c1.post1.dev1", "<=2"),
                ("2.0rc1", "<=2"),
                ("1", "<=2"),
                ("3.0.0a7", "<=3.0.0a8"),
                # Test the greater than operation
                ("3", ">2"),
                ("2.1", ">2.0"),
                ("2.0.1", ">2"),
                ("2.1.post1", ">2"),
                ("2.1+local.version", ">2"),
                ("3.0.0a8", ">3.0.0a7"),
                # Test the less than operation
                ("1", "<2"),
                ("2.0", "<2.1"),
                ("2.0.dev0", "<2.1"),
                ("3.0.0a7", "<3.0.0a8"),
                # Test the compatibility operation
                ("1", "~=1.0"),
                ("1.0.1", "~=1.0"),
                ("1.1", "~=1.0"),
                ("1.9999999", "~=1.0"),
                ("1.1", "~=1.0a1"),
                ("2022.01.01", "~=2022.01.01"),
                # Test that epochs are handled sanely
                ("2!1.0", "~=2!1.0"),
                ("2!1.0", "==2!1.*"),
                ("2!1.0", "==2!1.0"),
                ("2!1.0", "!=1.0"),
                ("2!1.0.0", "==2!1.0.0.0.*"),
                ("2!1.0.0", "==2!1.0.*"),
                ("2!1.0.0", "==2!1.*"),
                ("1.0", "!=2!1.0"),
                ("1.0", "<=2!0.1"),
                ("2!1.0", ">=2.0"),
                ("1.0", "<2!0.1"),
                ("2!1.0", ">2.0"),
                # Test some normalization rules
                ("2.0.5", ">2.0dev"),
            ]
        ]
        + [
            (v, s, False)
            for v, s in [
                # Test the equality operation
                ("2.1", "==2"),
                ("2.1", "==2.0"),
                ("2.1", "==2.0.0"),
                ("2.0", "==2.0+deadbeef"),
                # Test the equality operation with a prefix
                ("2.0", "==3.*"),
                ("2.1", "==2.0.*"),
                # Test the in-equality operation
                ("2.0", "!=2"),
                ("2.0", "!=2.0"),
                ("2.0", "!=2.0.0"),
                ("2.0+deadbeef", "!=2"),
                ("2.0+deadbeef", "!=2.0"),
                ("2.0+deadbeef", "!=2.0.0"),
                ("2.0+deadbeef", "!=2+deadbeef"),
                ("2.0+deadbeef", "!=2.0+deadbeef"),
                ("2.0+deadbeef", "!=2.0.0+deadbeef"),
                ("2.0+deadbeef.0", "!=2.0.0+deadbeef.00"),
                # Test the in-equality operation with a prefix
                ("2.dev1", "!=2.*"),
                ("2a1", "!=2.*"),
                ("2a1.post1", "!=2.*"),
                ("2b1", "!=2.*"),
                ("2b1.dev1", "!=2.*"),
                ("2c1", "!=2.*"),
                ("2c1.post1.dev1", "!=2.*"),
                ("2c1.post1.dev1", "!=2.0.*"),
                ("2rc1", "!=2.*"),
                ("2rc1", "!=2.0.*"),
                ("2", "!=2.*"),
                ("2", "!=2.0.*"),
                ("2.0", "!=2.*"),
                ("2.0.0", "!=2.*"),
                # Test the greater than equal operation
                ("2.0.dev1", ">=2"),
                ("2.0a1", ">=2"),
                ("2.0a1.dev1", ">=2"),
                ("2.0b1", ">=2"),
                ("2.0b1.post1", ">=2"),
                ("2.0c1", ">=2"),
                ("2.0c1.post1.dev1", ">=2"),
                ("2.0rc1", ">=2"),
                ("1", ">=2"),
                # Test the less than equal operation
                ("2.0.post1", "<=2"),
                ("2.0.post1.dev1", "<=2"),
                ("3", "<=2"),
                # Test the greater than operation
                ("1", ">2"),
                ("2.0.dev1", ">2"),
                ("2.0a1", ">2"),
                ("2.0a1.post1", ">2"),
                ("2.0b1", ">2"),
                ("2.0b1.dev1", ">2"),
                ("2.0c1", ">2"),
                ("2.0c1.post1.dev1", ">2"),
                ("2.0rc1", ">2"),
                ("2.0", ">2"),
                ("2.0.post1", ">2"),
                ("2.0.post1.dev1", ">2"),
                ("2.0+local.version", ">2"),
                # Test the less than operation
                ("2.0.dev1", "<2"),
                ("2.0a1", "<2"),
                ("2.0a1.post1", "<2"),
                ("2.0b1", "<2"),
                ("2.0b2.dev1", "<2"),
                ("2.0c1", "<2"),
                ("2.0c1.post1.dev1", "<2"),
                ("2.0rc1", "<2"),
                ("2.0", "<2"),
                ("2.post1", "<2"),
                ("2.post1.dev1", "<2"),
                ("3", "<2"),
                # Test the compatibility operation
                ("2.0", "~=1.0"),
                ("1.1.0", "~=1.0.0"),
                ("1.1.post1", "~=1.0.0"),
                # Test that epochs are handled sanely
                ("1.0", "~=2!1.0"),
                ("2!1.0", "~=1.0"),
                ("2!1.0", "==1.0"),
                ("1.0", "==2!1.0"),
                ("2!1.0", "==1.0.0.*"),
                ("1.0", "==2!1.0.0.*"),
                ("2!1.0", "==1.*"),
                ("1.0", "==2!1.*"),
                ("2!1.0", "!=2!1.0"),
            ]
        ],
    )
    def test_specifiers(self, version, spec, expected):
        spec = Specifier(spec, prereleases=True)

        if expected:
            # Test that the plain string form works
            assert version in spec
            assert spec.contains(version)

            # Test that the version instance form works
            assert Version(version) in spec
            assert spec.contains(Version(version))
        else:
            # Test that the plain string form works
            assert version not in spec
            assert not spec.contains(version)

            # Test that the version instance form works
            assert Version(version) not in spec
            assert not spec.contains(Version(version))

    @pytest.mark.parametrize(
        ("spec", "version"),
        [
            ("==1.0", "not a valid version"),
            ("===invalid", "invalid"),
        ],
    )
    def test_invalid_spec(self, spec, version):
        spec = Specifier(spec, prereleases=True)
        assert not spec.contains(version)

    @pytest.mark.parametrize(
        (
            "specifier",
            "initial_prereleases",
            "set_prereleases",
            "version",
            "initial_contains",
            "final_contains",
        ),
        [
            (">1.0", None, True, "1.0.dev1", False, False),
            (">1.0", None, True, "2.0.dev1", True, True),
            # Setting prereleases to True explicitly includes prerelease versions
            (">1.0", None, True, "2.0.dev1", True, True),
            (">1.0", False, True, "2.0.dev1", False, True),
            # Setting prereleases to False explicitly excludes prerelease versions
            (">1.0", None, False, "2.0.dev1", True, False),
            (">1.0", True, False, "2.0.dev1", True, False),
            # Setting prereleases to None falls back to default behavior
            (">1.0", True, None, "2.0.dev1", True, True),
            (">1.0", False, None, "2.0.dev1", False, True),
            # Different specifiers with prerelease versions
            (">=2.0.dev1", None, True, "2.0a1", True, True),
            (">=2.0.dev1", None, False, "2.0a1", True, False),
            # Alpha/beta/rc/dev variations
            (">1.0", None, True, "2.0a1", True, True),
            (">1.0", None, True, "2.0b1", True, True),
            (">1.0", None, True, "2.0rc1", True, True),
            # Edge cases
            ("==2.0.*", None, True, "2.0.dev1", True, True),
            ("==2.0.*", None, False, "2.0.dev1", True, False),
            # Specifiers that already include prereleases implicitly
            ("<1.0.dev1", None, False, "0.9.dev1", True, False),
            (">1.0.dev1", None, None, "1.1.dev1", True, True),
            # Multiple changes to the prereleases setting
            (">1.0", True, False, "2.0.dev1", True, False),
            (">1.0", False, None, "2.0.dev1", False, True),
        ],
    )
    def test_specifier_prereleases_set(
        self,
        specifier,
        initial_prereleases,
        set_prereleases,
        version,
        initial_contains,
        final_contains,
    ):
        """Test setting prereleases property."""
        spec = Specifier(specifier, prereleases=initial_prereleases)

        assert (version in spec) == initial_contains
        assert spec.contains(version) == initial_contains

        spec.prereleases = set_prereleases

        assert (version in spec) == final_contains
        assert spec.contains(version) == final_contains

    @pytest.mark.parametrize(
        ("version", "spec", "expected"),
        [
            ("1.0.0", "===1.0", False),
            ("1.0.dev0", "===1.0", False),
            # Test identity comparison by itself
            ("1.0", "===1.0", True),
            ("1.0.dev0", "===1.0.dev0", True),
        ],
    )
    def test_specifiers_identity(self, version, spec, expected):
        spec = Specifier(spec)

        if expected:
            # Identity comparisons only support the plain string form
            assert version in spec
        else:
            # Identity comparisons only support the plain string form
            assert version not in spec

    @pytest.mark.parametrize(
        ("specifier", "expected"),
        [
            ("==1.0", False),
            (">=1.0", False),
            ("<=1.0", False),
            ("~=1.0", False),
            ("<1.0", False),
            (">1.0", False),
            ("<1.0.dev1", True),
            (">1.0.dev1", True),
            ("!=1.0.dev1", False),
            ("==1.0.*", False),
            ("==1.0.dev1", True),
            (">=1.0.dev1", True),
            ("<=1.0.dev1", True),
            ("~=1.0.dev1", True),
        ],
    )
    def test_specifier_prereleases_detection(self, specifier, expected):
        assert Specifier(specifier).prereleases == expected

    @pytest.mark.parametrize(
        ("specifier", "version", "spec_pre", "contains_pre", "expected"),
        [
            (">=1.0", "2.0.dev1", None, None, True),
            (">=2.0.dev1", "2.0a1", None, None, True),
            ("==2.0.*", "2.0a1.dev1", None, None, True),
            ("<=2.0", "1.0.dev1", None, None, True),
            ("<=2.0.dev1", "1.0a1", None, None, True),
            ("<2.0", "2.0a1", None, None, False),
            ("<2.0a2", "2.0a1", None, None, True),
            ("<=2.0", "1.0.dev1", False, None, False),
            ("<=2.0a1", "1.0.dev1", False, None, False),
            ("<=2.0", "1.0.dev1", None, False, False),
            ("<=2.0a1", "1.0.dev1", None, False, False),
            ("<=2.0", "1.0.dev1", True, False, False),
            ("<=2.0a1", "1.0.dev1", True, False, False),
            ("<=2.0", "1.0.dev1", False, True, True),
            ("<=2.0a1", "1.0.dev1", False, True, True),
        ],
    )
    def test_specifiers_prereleases(
        self, specifier, version, spec_pre, contains_pre, expected
    ):
        spec = Specifier(specifier, prereleases=spec_pre)

        assert spec.contains(version, prereleases=contains_pre) == expected

    @pytest.mark.parametrize(
        ("specifier", "specifier_prereleases", "prereleases", "input", "expected"),
        [
            # General test of the filter method
            (">=1.0.dev1", None, None, ["1.0", "2.0a1"], ["1.0", "2.0a1"]),
            (">=1.2.3", None, None, ["1.2", "1.5a1"], ["1.5a1"]),
            (">=1.2.3", None, None, ["1.3", "1.5a1"], ["1.3"]),
            (">=1.0", None, None, ["2.0a1"], ["2.0a1"]),
            ("!=2.0a1", None, None, ["1.0a2", "1.0", "2.0a1"], ["1.0"]),
            ("==2.0a1", None, None, ["2.0a1"], ["2.0a1"]),
            (">2.0a1", None, None, ["2.0a1", "3.0a2", "3.0"], ["3.0a2", "3.0"]),
            ("<2.0a1", None, None, ["1.0a2", "1.0", "2.0a1"], ["1.0a2", "1.0"]),
            ("~=2.0a1", None, None, ["1.0", "2.0a1", "3.0a2", "3.0"], ["2.0a1"]),
            # Test overriding with the prereleases parameter on filter
            (">=1.0.dev1", None, False, ["1.0", "2.0a1"], ["1.0"]),
            # Test overriding with the overall specifier
            (">=1.0.dev1", True, None, ["1.0", "2.0a1"], ["1.0", "2.0a1"]),
            (">=1.0.dev1", False, None, ["1.0", "2.0a1"], ["1.0"]),
            # Test when both specifier and filter have prerelease value
            (">=1.0", True, False, ["1.0", "2.0a1"], ["1.0"]),
            (">=1.0", False, True, ["1.0", "2.0a1"], ["1.0", "2.0a1"]),
            (">=1.0", True, True, ["1.0", "2.0a1"], ["1.0", "2.0a1"]),
            (">=1.0", False, False, ["1.0", "2.0a1"], ["1.0"]),
            # Test that invalid versions are discarded
            (">=1.0", None, None, ["not a valid version"], []),
            (">=1.0", None, None, ["1.0", "not a valid version"], ["1.0"]),
        ],
    )
    def test_specifier_filter(
        self, specifier, specifier_prereleases, prereleases, input, expected
    ):
        if specifier_prereleases is None:
            spec = Specifier(specifier)
        else:
            spec = Specifier(specifier, prereleases=specifier_prereleases)

        kwargs = {"prereleases": prereleases} if prereleases is not None else {}

        assert list(spec.filter(input, **kwargs)) == expected

    @pytest.mark.parametrize(
        ("spec", "op"),
        [
            ("~=2.0", "~="),
            ("==2.1.*", "=="),
            ("==2.1.0.3", "=="),
            ("!=2.2.*", "!="),
            ("!=2.2.0.5", "!="),
            ("<=5", "<="),
            (">=7.9a1", ">="),
            ("<1.0.dev1", "<"),
            (">2.0.post1", ">"),
            # === is an escape hatch in PEP 440
            ("===lolwat", "==="),
        ],
    )
    def test_specifier_operator_property(self, spec, op):
        assert Specifier(spec).operator == op

    @pytest.mark.parametrize(
        ("spec", "version"),
        [
            ("~=2.0", "2.0"),
            ("==2.1.*", "2.1.*"),
            ("==2.1.0.3", "2.1.0.3"),
            ("!=2.2.*", "2.2.*"),
            ("!=2.2.0.5", "2.2.0.5"),
            ("<=5", "5"),
            (">=7.9a1", "7.9a1"),
            ("<1.0.dev1", "1.0.dev1"),
            (">2.0.post1", "2.0.post1"),
            # === is an escape hatch in PEP 440
            ("===lolwat", "lolwat"),
        ],
    )
    def test_specifier_version_property(self, spec, version):
        assert Specifier(spec).version == version

    @pytest.mark.parametrize(
        ("spec", "expected_length"),
        [("", 0), ("==2.0", 1), (">=2.0", 1), (">=2.0,<3", 2), (">=2.0,<3,==2.4", 3)],
    )
    def test_length(self, spec, expected_length):
        spec = SpecifierSet(spec)
        assert len(spec) == expected_length

    @pytest.mark.parametrize(
        ("spec", "expected_items"),
        [
            ("", []),
            ("==2.0", ["==2.0"]),
            (">=2.0", [">=2.0"]),
            (">=2.0,<3", [">=2.0", "<3"]),
            (">=2.0,<3,==2.4", [">=2.0", "<3", "==2.4"]),
        ],
    )
    def test_iteration(self, spec, expected_items):
        spec = SpecifierSet(spec)
        items = {str(item) for item in spec}
        assert items == set(expected_items)

    def test_specifier_equal_for_compatible_operator(self):
        assert Specifier("~=1.18.0") != Specifier("~=1.18")

    def test_specifier_hash_for_compatible_operator(self):
        assert hash(Specifier("~=1.18.0")) != hash(Specifier("~=1.18"))


class TestSpecifierSet:
    @pytest.mark.parametrize("version", VERSIONS)
    def test_empty_specifier(self, version):
        spec = SpecifierSet(prereleases=True)

        assert version in spec
        assert spec.contains(version)
        assert parse(version) in spec
        assert spec.contains(parse(version))

    def test_create_from_specifiers(self):
        spec_strs = [">=1.0", "!=1.1", "!=1.2", "<2.0"]
        specs = [Specifier(s) for s in spec_strs]
        spec = SpecifierSet(iter(specs))
        assert set(spec) == set(specs)

    @pytest.mark.parametrize(
        (
            "initial_prereleases",
            "set_prereleases",
            "version",
            "initial_contains",
            "final_contains",
            "spec_str",
        ),
        [
            (None, True, "1.0.dev1", True, True, ""),
            (False, True, "1.0.dev1", False, True, ""),
            # Setting prerelease from True to False
            (True, False, "1.0.dev1", True, False, ""),
            (True, False, "1.0.dev1", False, False, ">=1.0"),
            (True, False, "1.0.dev1", True, False, "==1.*"),
            # Setting prerelease from False to None
            (False, None, "1.0.dev1", False, True, ""),
            (False, None, "2.0.dev1", False, True, ">=1.0"),
            # Setting prerelease from True to None
            (True, None, "1.0.dev1", True, True, ""),
            (True, None, "2.0.dev1", True, True, ">=1.0"),
            # Various version patterns with different transitions
            (None, True, "2.0b1", True, True, ""),
            (None, False, "2.0a1", True, False, ""),
            (True, False, "1.0rc1", True, False, ""),
            (False, True, "1.0.post1.dev1", False, True, ""),
            # Specifiers that include prerelease versions explicitly
            (None, False, "2.0.dev1", True, False, "==2.0.dev1"),
            (True, False, "1.0.dev1", True, False, "==1.0.*"),
            (False, True, "1.0.dev1", False, True, "!=2.0"),
            # SpecifierSet with multiple specifiers
            (None, True, "1.5a1", True, True, ">=1.0,<2.0"),
            (False, True, "1.5b1", False, True, ">=1.0,<2.0"),
            (True, False, "1.5rc1", True, False, ">=1.0,<2.0"),
            # Test with dev/alpha/beta/rc variations
            (None, True, "1.0a1", True, True, ""),
            (None, True, "1.0b2", True, True, ""),
            (None, True, "1.0rc3", True, True, ""),
            (None, True, "1.0.dev4", True, True, ""),
            # Test with specifiers that have prereleases implicitly
            (None, False, "1.0a1", True, False, ">=1.0a1"),
            (None, False, "0.9.dev0", True, False, "<1.0.dev1"),
        ],
    )
    def test_specifier_prereleases_explicit(
        self,
        initial_prereleases,
        set_prereleases,
        version,
        initial_contains,
        final_contains,
        spec_str,
    ):
        """Test setting prereleases property with different initial states."""
        spec = SpecifierSet(spec_str, prereleases=initial_prereleases)

        assert (version in spec) == initial_contains
        assert spec.contains(version) == initial_contains

        spec.prereleases = set_prereleases

        assert (version in spec) == final_contains
        assert spec.contains(version) == final_contains

    def test_specifier_contains_prereleases(self):
        spec = SpecifierSet()
        assert spec.prereleases is None
        assert spec.contains("1.0.dev1")
        assert spec.contains("1.0.dev1", prereleases=True)

        spec = SpecifierSet(prereleases=True)
        assert spec.prereleases
        assert spec.contains("1.0.dev1")
        assert not spec.contains("1.0.dev1", prereleases=False)

    @pytest.mark.parametrize(
        (
            "specifier",
            "version",
            "spec_prereleases",
            "contains_prereleases",
            "installed",
            "expected",
        ),
        [
            ("~=1.0", "1.1.0.dev1", None, None, True, True),
            ("~=1.0", "1.1.0.dev1", False, False, True, True),
            ("~=1.0", "1.1.0.dev1", True, False, True, True),
            ("~=1.0", "1.1.0.dev1", None, False, True, True),
            # Case when installed=False:
            ("~=1.0", "1.1.0.dev1", True, None, False, True),
            ("~=1.0", "1.1.0.dev1", None, True, False, True),
            ("~=1.0", "1.1.0.dev1", False, True, False, True),
            ("~=1.0", "1.1.0.dev1", False, False, False, False),
            ("~=1.0", "1.1.0.dev1", None, False, False, False),
            # Test with different version types
            ("~=1.0", "1.1.0a1", None, None, True, True),
            ("~=1.0", "1.1.0b1", None, None, True, True),
            ("~=1.0", "1.1.0rc1", None, None, True, True),
            ("~=1.0", "1.1.0.post1.dev1", None, None, True, True),
            # Test with different specifiers
            (">=1.0", "2.0.dev1", None, None, True, True),
            ("==1.*", "1.5.0a1", None, None, True, True),
            (">=1.0,<3.0", "2.0.dev1", None, None, True, True),
            ("!=2.0", "2.0.dev1", None, None, True, True),
            # Test with non-matching versions (regardless of installed)
            ("~=1.0", "3.0.0.dev1", None, None, True, False),
            ("~=1.0", "3.0.0.dev1", True, None, True, False),
            ("~=1.0", "3.0.0.dev1", None, True, True, False),
            ("~=1.0", "3.0.0.dev1", True, True, True, False),
            ("~=1.0", "3.0.0.dev1", False, False, True, False),
            ("~=1.0", "3.0.0.dev1", None, None, False, False),
            # Test with versions outside specifier but with prereleases
            (">=2.0", "1.9.0.dev1", True, None, True, False),
            (">=2.0", "1.9.0.dev1", None, True, True, False),
            (">=2.0", "1.9.0.dev1", True, True, True, False),
            (">=2.0", "1.9.0.dev1", None, None, False, False),
            # Test with edge versions
            (">=1.0", "1.0.0.dev1", None, None, True, False),
            ("<=1.0", "1.0.0.dev1", None, None, True, True),
            ("<1.0", "1.0.0.dev1", None, None, True, False),
            ("<1.0", "0.9.0.dev1", None, None, True, True),
            # Test with specifiers that have explicit prereleases
            (">=1.0.dev1", "1.0.0.dev1", None, None, True, True),
            (">=1.0.dev1", "1.0.0.dev1", False, False, False, False),
            ("==1.0.0.dev1", "1.0.0.dev1", False, False, False, False),
            # Test with stable versions
            ("~=1.0", "1.1.0", None, None, True, True),
            ("~=1.0", "1.1.0", False, False, False, True),
            ("~=1.0", "1.1.0", True, False, False, True),
            # Test combinations of prereleases=True/False and installed=True/False
            ("~=1.0", "1.1.0.dev1", True, None, False, True),
            ("~=1.0", "1.1.0.dev1", False, None, False, False),
            ("~=1.0", "1.1.0.dev1", None, True, False, True),
            ("~=1.0", "1.1.0.dev1", None, False, False, False),
            ("~=1.0", "1.1.0.dev1", True, False, False, False),
            ("~=1.0", "1.1.0.dev1", False, True, False, True),
            # Test conflicting prereleases and contain_prereleases
            ("~=1.0", "1.1.0.dev1", True, False, False, False),
            ("~=1.0", "1.1.0.dev1", False, True, False, True),
            # Test with specifiers that explicitly have prereleases overridden
            (">=1.0.dev1", "1.0.0.dev1", None, False, False, False),
            (">=1.0.dev1", "1.0.0.dev1", False, None, False, False),
        ],
    )
    def test_specifier_contains_installed_prereleases(
        self,
        specifier,
        version,
        spec_prereleases,
        contains_prereleases,
        installed,
        expected,
    ):
        """Test the behavior of SpecifierSet.contains with installed and prereleases."""
        spec = SpecifierSet(specifier, prereleases=spec_prereleases)

        kwargs = {}
        if contains_prereleases is not None:
            kwargs["prereleases"] = contains_prereleases
        if installed is not None:
            kwargs["installed"] = installed

        assert spec.contains(version, **kwargs) == expected

        spec = SpecifierSet("~=1.0", prereleases=False)
        assert spec.contains("1.1.0.dev1", installed=True)
        assert not spec.contains("1.1.0.dev1", prereleases=False, installed=False)

    @pytest.mark.parametrize(
        ("specifier", "specifier_prereleases", "prereleases", "input", "expected"),
        [
            # General test of the filter method
            ("", None, None, ["1.0", "2.0a1"], ["1.0"]),
            (">=1.0.dev1", None, None, ["1.0", "2.0a1"], ["1.0", "2.0a1"]),
            ("", None, None, ["1.0a1"], ["1.0a1"]),
            (">=1.2.3", None, None, ["1.2", "1.5a1"], ["1.5a1"]),
            (">=1.2.3", None, None, ["1.3", "1.5a1"], ["1.3"]),
            ("", None, None, ["1.0", Version("2.0")], ["1.0", Version("2.0")]),
            (">=1.0", None, None, ["2.0a1"], ["2.0a1"]),
            ("!=2.0a1", None, None, ["1.0a2", "1.0", "2.0a1"], ["1.0"]),
            ("==2.0a1", None, None, ["2.0a1"], ["2.0a1"]),
            (">2.0a1", None, None, ["2.0a1", "3.0a2", "3.0"], ["3.0a2", "3.0"]),
            ("<2.0a1", None, None, ["1.0a2", "1.0", "2.0a1"], ["1.0a2", "1.0"]),
            ("~=2.0a1", None, None, ["1.0", "2.0a1", "3.0a2", "3.0"], ["2.0a1"]),
            # Test overriding with the prereleases parameter on filter
            ("", None, False, ["1.0a1"], []),
            (">=1.0.dev1", None, False, ["1.0", "2.0a1"], ["1.0"]),
            ("", None, True, ["1.0", "2.0a1"], ["1.0", "2.0a1"]),
            # Test overriding with the overall specifier
            ("", True, None, ["1.0", "2.0a1"], ["1.0", "2.0a1"]),
            ("", False, None, ["1.0", "2.0a1"], ["1.0"]),
            (">=1.0.dev1", True, None, ["1.0", "2.0a1"], ["1.0", "2.0a1"]),
            (">=1.0.dev1", False, None, ["1.0", "2.0a1"], ["1.0"]),
            ("", True, None, ["1.0a1"], ["1.0a1"]),
            ("", False, None, ["1.0a1"], []),
            # Test when both specifier and filter have prerelease value
            (">=1.0", True, False, ["1.0", "2.0a1"], ["1.0"]),
            (">=1.0", False, True, ["1.0", "2.0a1"], ["1.0", "2.0a1"]),
            (">=1.0", True, True, ["1.0", "2.0a1"], ["1.0", "2.0a1"]),
            (">=1.0", False, False, ["1.0", "2.0a1"], ["1.0"]),
            # Test when there are multiple specifiers
            (">=1.0,<=2.0", None, None, ["1.0", "1.5a1"], ["1.0"]),
            (">=1.0,<=2.0dev", None, None, ["1.0", "1.5a1"], ["1.0", "1.5a1"]),
            (">=1.0,<=2.0", True, None, ["1.0", "1.5a1"], ["1.0", "1.5a1"]),
            (">=1.0,<=2.0", False, None, ["1.0", "1.5a1"], ["1.0"]),
            (">=1.0,<=2.0dev", False, None, ["1.0", "1.5a1"], ["1.0"]),
            (">=1.0,<=2.0dev", True, None, ["1.0", "1.5a1"], ["1.0", "1.5a1"]),
            (">=1.0,<=2.0", None, False, ["1.0", "1.5a1"], ["1.0"]),
            (">=1.0,<=2.0", None, True, ["1.0", "1.5a1"], ["1.0", "1.5a1"]),
            (">=1.0,<=2.0dev", None, False, ["1.0", "1.5a1"], ["1.0"]),
            (">=1.0,<=2.0dev", None, True, ["1.0", "1.5a1"], ["1.0", "1.5a1"]),
            (">=1.0,<=2.0", True, False, ["1.0", "1.5a1"], ["1.0"]),
            (">=1.0,<=2.0", False, True, ["1.0", "1.5a1"], ["1.0", "1.5a1"]),
            (">=1.0,<=2.0dev", True, False, ["1.0", "1.5a1"], ["1.0"]),
            (">=1.0,<=2.0dev", False, True, ["1.0", "1.5a1"], ["1.0", "1.5a1"]),
            # Test that invalid versions are discarded
            ("", None, None, ["invalid version"], []),
            ("", None, False, ["invalid version"], []),
            ("", False, None, ["invalid version"], []),
            ("", None, None, ["1.0", "invalid version"], ["1.0"]),
            ("", None, False, ["1.0", "invalid version"], ["1.0"]),
            ("", False, None, ["1.0", "invalid version"], ["1.0"]),
        ],
    )
    def test_specifier_filter(
        self, specifier, specifier_prereleases, prereleases, input, expected
    ):
        if specifier_prereleases is None:
            spec = SpecifierSet(specifier)
        else:
            spec = SpecifierSet(specifier, prereleases=specifier_prereleases)

        kwargs = {"prereleases": prereleases} if prereleases is not None else {}

        assert list(spec.filter(input, **kwargs)) == expected

    @pytest.mark.parametrize(
        ("specifier", "prereleases", "input", "expected"),
        [
            # !=1.*, !=2.*, !=3.0 leaves gap at 3.0 prereleases
            (
                ">=1,!=1.*,!=2.*,!=3.0,<=3.0",
                None,
                ["3.0.dev0", "3.0a1"],
                ["3.0.dev0", "3.0a1"],
            ),
            (
                ">=1,!=1.*,!=2.*,!=3.0,<=3.0",
                None,
                ["0.9", "3.0.dev0", "3.0a1", "4.0"],
                ["3.0.dev0", "3.0a1"],
            ),
            (
                ">=1,!=1.*,!=2.*,!=3.0,<=3.0",
                True,
                ["0.9", "3.0.dev0", "3.0a1", "4.0"],
                ["3.0.dev0", "3.0a1"],
            ),
            (
                ">=1,!=1.*,!=2.*,!=3.0,<=3.0",
                False,
                ["0.9", "3.0.dev0", "3.0a1", "4.0"],
                [],
            ),
            # >=1.0a1,!=1.*,!=2.*,<3.0 has no matching versions
            # because <3.0 excludes 3.0 prereleases
            (
                ">=1.0a1,!=1.*,!=2.*,<3.0",
                None,
                ["1.0a1", "2.0a1", "3.0a1"],
                [],
            ),
            (
                ">=1.0a1,!=1.*,!=2.*,<3.0",
                True,
                ["1.0a1", "2.0a1", "3.0a1"],
                [],
            ),
            (
                ">=1.0a1,!=1.*,!=2.*,<3.0",
                False,
                ["1.0a1", "2.0a1", "3.0a1"],
                [],
            ),
            # >=1.0.dev0,!=1.*,!=2.*,<3.0.dev0 has no matching versions
            (
                ">=1.0.dev0,!=1.*,!=2.*,<3.0.dev0",
                None,
                ["1.0.dev0", "2.0.dev0", "3.0.dev0"],
                [],
            ),
            (
                ">=1.0.dev0,!=1.*,!=2.*,<3.0.dev0",
                True,
                ["1.0.dev0", "2.0.dev0", "3.0.dev0"],
                [],
            ),
            (
                ">=1.0.dev0,!=1.*,!=2.*,<3.0.dev0",
                False,
                ["1.0.dev0", "2.0.dev0", "3.0.dev0"],
                [],
            ),
            # Gaps with post-releases
            (
                ">=1.0,!=1.0,!=1.1,<2.0",
                None,
                ["1.0.post1", "1.1.post1"],
                ["1.0.post1", "1.1.post1"],
            ),
            (
                ">=1.0,!=1.0,!=1.1,<2.0",
                None,
                ["0.9", "1.0.post1", "1.1.post1", "2.0"],
                ["1.0.post1", "1.1.post1"],
            ),
            (
                ">=1.0,!=1.0,!=1.1,<2.0",
                True,
                ["0.9", "1.0.post1", "1.1.post1", "2.0"],
                ["1.0.post1", "1.1.post1"],
            ),
            (
                ">=1.0,!=1.0,!=1.1,<2.0",
                False,
                ["0.9", "1.0.post1", "1.1.post1", "2.0"],
                ["1.0.post1", "1.1.post1"],
            ),
            # Dev version gaps
            (
                ">=1,!=1.*,!=2.*,!=3.0,!=3.1,<4",
                None,
                ["3.0.dev0", "3.1.dev0"],
                ["3.0.dev0", "3.1.dev0"],
            ),
            (
                ">=1,!=1.*,!=2.*,!=3.0,!=3.1,<4",
                None,
                ["0.5", "3.0.dev0", "3.1.dev0", "5.0"],
                ["3.0.dev0", "3.1.dev0"],
            ),
            (
                ">=1,!=1.*,!=2.*,!=3.0,!=3.1,<4",
                True,
                ["0.5", "3.0.dev0", "3.1.dev0", "5.0"],
                ["3.0.dev0", "3.1.dev0"],
            ),
            (
                ">=1,!=1.*,!=2.*,!=3.0,!=3.1,<4",
                False,
                ["0.5", "3.0.dev0", "3.1.dev0", "5.0"],
                [],
            ),
            # Test that < (exclusive) excludes prereleases of the specified version
            # but allows prereleases of earlier versions.
            # <1.1 excludes 1.1.dev0, 1.1a1, etc. but allows 1.0a1, 1.0b1
            (
                ">=1.0a1,!=1.0,<1.1",
                None,
                ["1.0a1", "1.0b1"],
                ["1.0a1", "1.0b1"],
            ),
            (
                ">=1.0a1,!=1.0,<1.1",
                None,
                ["0.9", "1.0a1", "1.0b1", "1.1"],
                ["1.0a1", "1.0b1"],
            ),
            (
                ">=1.0a1,!=1.0,<1.1",
                None,
                ["1.0a1", "1.0b1", "1.1.dev0", "1.1a1"],
                ["1.0a1", "1.0b1"],
            ),
            (
                ">=1.0a1,!=1.0,<1.1",
                True,
                ["0.9", "1.0a1", "1.0b1", "1.1"],
                ["1.0a1", "1.0b1"],
            ),
            (
                ">=1.0a1,!=1.0,<1.1",
                True,
                ["1.0a1", "1.0b1", "1.1.dev0", "1.1a1"],
                ["1.0a1", "1.0b1"],
            ),
            (
                ">=1.0a1,!=1.0,<1.1",
                False,
                ["0.9", "1.0a1", "1.0b1", "1.1"],
                [],
            ),
            # Test that <= (inclusive) allows prereleases of the specified version
            # when explicitly requested, but follows default prerelease filtering
            # when prereleases=None (excludes them if final releases present)
            (
                ">=0.9,!=0.9,<=1.0",
                None,
                ["0.9.post1", "1.0.dev0", "1.0a1", "1.0"],
                [
                    "0.9.post1",
                    "1.0",
                ],  # prereleases filtered out due to presence of final release
            ),
            (
                ">=0.9,!=0.9,<=1.0",
                None,
                ["0.9.post1", "1.0.dev0", "1.0a1", "1.0", "1.0.post1"],
                [
                    "0.9.post1",
                    "1.0",
                ],  # dev/alpha filtered out; post-releases not included with <=
            ),
            (
                ">=0.9,!=0.9,<=1.0",
                True,
                ["0.9.post1", "1.0.dev0", "1.0a1", "1.0", "1.1"],
                [
                    "0.9.post1",
                    "1.0.dev0",
                    "1.0a1",
                    "1.0",
                ],  # includes prereleases when explicitly True
            ),
            (
                ">=0.9,!=0.9,<=1.0",
                False,
                ["0.9.post1", "1.0.dev0", "1.0a1", "1.0", "1.1"],
                ["0.9.post1", "1.0"],
            ),
            # Epoch-based gaps
            (
                ">=1!0,!=1!1.*,!=1!2.*,<1!3",
                None,
                ["1!0.5", "1!2.5"],
                ["1!0.5"],
            ),
            (
                ">=1!0,!=1!1.*,!=1!2.*,<1!3",
                None,
                ["0!5.0", "1!0.5", "1!2.5", "2!0.0"],
                ["1!0.5"],
            ),
            (
                ">=1!0,!=1!1.*,!=1!2.*,<1!3",
                True,
                ["0!5.0", "1!0.5", "1!2.5", "2!0.0"],
                ["1!0.5"],
            ),
            (
                ">=1!0,!=1!1.*,!=1!2.*,<1!3",
                False,
                ["0!5.0", "1!0.5", "1!2.5", "2!0.0"],
                ["1!0.5"],
            ),
        ],
    )
    def test_filter_exclusionary_bridges(self, specifier, prereleases, input, expected):
        """
        Test that filter correctly handles exclusionary bridges.

        When specifiers exclude certain version ranges (e.g., !=1.*, !=2.*),
        there may be "gaps" where only prerelease, dev, or post versions match.
        The filter should return these matching versions regardless of whether
        non-matching non-prerelease versions are present in the input.
        """
        spec = SpecifierSet(specifier)
        kwargs = {"prereleases": prereleases} if prereleases is not None else {}
        assert list(spec.filter(input, **kwargs)) == expected

    @pytest.mark.parametrize(
        ("specifier", "prereleases", "version", "expected"),
        [
            # !=1.*, !=2.*, !=3.0 leaves gap at 3.0 prereleases
            (">=1,!=1.*,!=2.*,!=3.0,<=3.0", None, "3.0.dev0", True),
            (">=1,!=1.*,!=2.*,!=3.0,<=3.0", None, "3.0a1", True),
            (">=1,!=1.*,!=2.*,!=3.0,<=3.0", True, "3.0.dev0", True),
            (">=1,!=1.*,!=2.*,!=3.0,<=3.0", True, "3.0a1", True),
            (">=1,!=1.*,!=2.*,!=3.0,<=3.0", False, "3.0.dev0", False),
            (">=1,!=1.*,!=2.*,!=3.0,<=3.0", False, "3.0a1", False),
            # Versions outside the gap should not match
            (">=1,!=1.*,!=2.*,!=3.0,<=3.0", None, "0.9", False),
            (">=1,!=1.*,!=2.*,!=3.0,<=3.0", None, "1.0", False),
            (">=1,!=1.*,!=2.*,!=3.0,<=3.0", None, "2.0", False),
            (">=1,!=1.*,!=2.*,!=3.0,<=3.0", None, "3.0", False),
            (">=1,!=1.*,!=2.*,!=3.0,<=3.0", None, "4.0", False),
            # >=1.0a1,!=1.*,!=2.*,<3.0 has no matching versions
            # because <3.0 excludes 3.0 prereleases
            (">=1.0a1,!=1.*,!=2.*,<3.0", None, "1.0a1", False),
            (">=1.0a1,!=1.*,!=2.*,<3.0", None, "2.0a1", False),
            (">=1.0a1,!=1.*,!=2.*,<3.0", None, "3.0a1", False),
            (">=1.0a1,!=1.*,!=2.*,<3.0", True, "1.0a1", False),
            (">=1.0a1,!=1.*,!=2.*,<3.0", True, "2.0a1", False),
            (">=1.0a1,!=1.*,!=2.*,<3.0", False, "1.0a1", False),
            (">=1.0a1,!=1.*,!=2.*,<3.0", False, "2.0a1", False),
            # >=1.0.dev0,!=1.*,!=2.*,<3.0.dev0 has no matching versions
            (">=1.0.dev0,!=1.*,!=2.*,<3.0.dev0", None, "1.0.dev0", False),
            (">=1.0.dev0,!=1.*,!=2.*,<3.0.dev0", None, "2.0.dev0", False),
            (">=1.0.dev0,!=1.*,!=2.*,<3.0.dev0", None, "3.0.dev0", False),
            (">=1.0.dev0,!=1.*,!=2.*,<3.0.dev0", True, "1.0.dev0", False),
            (">=1.0.dev0,!=1.*,!=2.*,<3.0.dev0", True, "2.0.dev0", False),
            (">=1.0.dev0,!=1.*,!=2.*,<3.0.dev0", False, "1.0.dev0", False),
            # Gaps with post-releases
            (">=1.0,!=1.0,!=1.1,<2.0", None, "1.0.post1", True),
            (">=1.0,!=1.0,!=1.1,<2.0", None, "1.1.post1", True),
            (">=1.0,!=1.0,!=1.1,<2.0", None, "1.0", False),
            (">=1.0,!=1.0,!=1.1,<2.0", None, "1.1", False),
            (">=1.0,!=1.0,!=1.1,<2.0", None, "2.0", False),
            (">=1.0,!=1.0,!=1.1,<2.0", True, "1.0.post1", True),
            (">=1.0,!=1.0,!=1.1,<2.0", True, "1.1.post1", True),
            (">=1.0,!=1.0,!=1.1,<2.0", False, "1.0.post1", True),
            (">=1.0,!=1.0,!=1.1,<2.0", False, "1.1.post1", True),
            # Dev version gaps
            (">=1,!=1.*,!=2.*,!=3.0,!=3.1,<4", None, "3.0.dev0", True),
            (">=1,!=1.*,!=2.*,!=3.0,!=3.1,<4", None, "3.1.dev0", True),
            (">=1,!=1.*,!=2.*,!=3.0,!=3.1,<4", None, "0.5", False),
            (">=1,!=1.*,!=2.*,!=3.0,!=3.1,<4", None, "3.0", False),
            (">=1,!=1.*,!=2.*,!=3.0,!=3.1,<4", None, "3.1", False),
            (">=1,!=1.*,!=2.*,!=3.0,!=3.1,<4", None, "5.0", False),
            (">=1,!=1.*,!=2.*,!=3.0,!=3.1,<4", True, "3.0.dev0", True),
            (">=1,!=1.*,!=2.*,!=3.0,!=3.1,<4", True, "3.1.dev0", True),
            (">=1,!=1.*,!=2.*,!=3.0,!=3.1,<4", False, "3.0.dev0", False),
            (">=1,!=1.*,!=2.*,!=3.0,!=3.1,<4", False, "3.1.dev0", False),
            # Test that < (exclusive) excludes prereleases of the specified version
            # but allows prereleases of earlier versions
            (">=1.0a1,!=1.0,<1.1", None, "1.0a1", True),
            (">=1.0a1,!=1.0,<1.1", None, "1.0b1", True),
            (">=1.0a1,!=1.0,<1.1", None, "0.9", False),
            (">=1.0a1,!=1.0,<1.1", None, "1.0", False),
            (">=1.0a1,!=1.0,<1.1", None, "1.1", False),
            (">=1.0a1,!=1.0,<1.1", None, "1.1.dev0", False),
            (">=1.0a1,!=1.0,<1.1", None, "1.1a1", False),
            (">=1.0a1,!=1.0,<1.1", True, "1.0a1", True),
            (">=1.0a1,!=1.0,<1.1", True, "1.0b1", True),
            (">=1.0a1,!=1.0,<1.1", True, "1.1.dev0", False),
            (">=1.0a1,!=1.0,<1.1", True, "1.1a1", False),
            (">=1.0a1,!=1.0,<1.1", False, "1.0a1", False),
            (">=1.0a1,!=1.0,<1.1", False, "1.0b1", False),
            # Test that <= (inclusive) allows prereleases of the specified version
            # when explicitly requested, but follows default prerelease filtering
            (">=0.9,!=0.9,<=1.0", None, "0.9.post1", True),
            (">=0.9,!=0.9,<=1.0", None, "1.0", True),
            (
                ">=0.9,!=0.9,<=1.0",
                None,
                "1.0.dev0",
                True,
            ),  # <= allows prereleases of specified version
            (
                ">=0.9,!=0.9,<=1.0",
                None,
                "1.0a1",
                True,
            ),  # <= allows prereleases of specified version
            (
                ">=0.9,!=0.9,<=1.0",
                None,
                "1.0.post1",
                False,
            ),  # 1.0.post1 > 1.0 so excluded by <=1.0
            (">=0.9,!=0.9,<=1.0", True, "0.9.post1", True),
            (">=0.9,!=0.9,<=1.0", True, "1.0.dev0", True),
            (">=0.9,!=0.9,<=1.0", True, "1.0a1", True),
            (">=0.9,!=0.9,<=1.0", True, "1.0", True),
            (">=0.9,!=0.9,<=1.0", False, "0.9.post1", True),
            (">=0.9,!=0.9,<=1.0", False, "1.0.dev0", False),
            (">=0.9,!=0.9,<=1.0", False, "1.0a1", False),
            (">=0.9,!=0.9,<=1.0", False, "1.0", True),
            # Epoch-based gaps
            (">=1!0,!=1!1.*,!=1!2.*,<1!3", None, "1!0.5", True),
            (">=1!0,!=1!1.*,!=1!2.*,<1!3", None, "1!2.5", False),
            (">=1!0,!=1!1.*,!=1!2.*,<1!3", None, "0!5.0", False),
            (">=1!0,!=1!1.*,!=1!2.*,<1!3", None, "2!0.0", False),
            (">=1!0,!=1!1.*,!=1!2.*,<1!3", True, "1!0.5", True),
            (">=1!0,!=1!1.*,!=1!2.*,<1!3", True, "0!5.0", False),
            (">=1!0,!=1!1.*,!=1!2.*,<1!3", False, "1!0.5", True),
            (">=1!0,!=1!1.*,!=1!2.*,<1!3", False, "0!5.0", False),
        ],
    )
    def test_contains_exclusionary_bridges(
        self, specifier, prereleases, version, expected
    ):
        """
        Test that contains correctly handles exclusionary bridges.

        When specifiers exclude certain version ranges (e.g., !=1.*, !=2.*),
        there may be "gaps" where only prerelease, dev, or post versions match.
        The contains method should return True for versions in these gaps
        when prereleases=None, following PEP 440 logic.
        """
        spec = SpecifierSet(specifier)
        kwargs = {"prereleases": prereleases} if prereleases is not None else {}
        assert spec.contains(version, **kwargs) == expected

    @pytest.mark.parametrize(
        ("specifier", "input"),
        [
            (">=1.0", "not a valid version"),
        ],
    )
    def test_contains_rejects_invalid_specifier(self, specifier, input):
        spec = SpecifierSet(specifier, prereleases=True)
        assert not spec.contains(input)

    @pytest.mark.parametrize(
        ("specifier", "expected"),
        [
            # Single item specifiers should just be reflexive
            ("!=2.0", "!=2.0"),
            ("<2.0", "<2.0"),
            ("<=2.0", "<=2.0"),
            ("==2.0", "==2.0"),
            (">2.0", ">2.0"),
            (">=2.0", ">=2.0"),
            ("~=2.0", "~=2.0"),
            # Spaces should be removed
            ("< 2", "<2"),
            # Multiple item specifiers should work
            ("!=2.0,>1.0", "!=2.0,>1.0"),
            ("!=2.0 ,>1.0", "!=2.0,>1.0"),
        ],
    )
    def test_specifiers_str_and_repr(self, specifier, expected):
        spec = SpecifierSet(specifier)

        assert str(spec) == expected
        assert repr(spec) == f"<SpecifierSet({expected!r})>"

    @pytest.mark.parametrize("specifier", SPECIFIERS + LEGACY_SPECIFIERS)
    def test_specifiers_hash(self, specifier):
        assert hash(SpecifierSet(specifier)) == hash(SpecifierSet(specifier))

    @pytest.mark.parametrize(
        ("left", "right", "expected"), [(">2.0", "<5.0", ">2.0,<5.0")]
    )
    def test_specifiers_combine(self, left, right, expected):
        result = SpecifierSet(left) & SpecifierSet(right)
        assert result == SpecifierSet(expected)

        result = SpecifierSet(left) & right
        assert result == SpecifierSet(expected)

        result = SpecifierSet(left, prereleases=True) & SpecifierSet(right)
        assert result == SpecifierSet(expected)
        assert result.prereleases

        result = SpecifierSet(left, prereleases=False) & SpecifierSet(right)
        assert result == SpecifierSet(expected)
        assert not result.prereleases

        result = SpecifierSet(left) & SpecifierSet(right, prereleases=True)
        assert result == SpecifierSet(expected)
        assert result.prereleases

        result = SpecifierSet(left) & SpecifierSet(right, prereleases=False)
        assert result == SpecifierSet(expected)
        assert not result.prereleases

        result = SpecifierSet(left, prereleases=True) & SpecifierSet(
            right, prereleases=True
        )
        assert result == SpecifierSet(expected)
        assert result.prereleases

        result = SpecifierSet(left, prereleases=False) & SpecifierSet(
            right, prereleases=False
        )
        assert result == SpecifierSet(expected)
        assert not result.prereleases

        with pytest.raises(ValueError):
            result = SpecifierSet(left, prereleases=True) & SpecifierSet(
                right, prereleases=False
            )

        with pytest.raises(ValueError):
            result = SpecifierSet(left, prereleases=False) & SpecifierSet(
                right, prereleases=True
            )

    def test_specifiers_combine_not_implemented(self):
        with pytest.raises(TypeError):
            SpecifierSet() & 12

    @pytest.mark.parametrize(
        ("left", "right", "op"),
        itertools.chain.from_iterable(
            # Verify that the equal (==) operator works correctly
            [[(x, x, operator.eq) for x in SPECIFIERS]]
            +
            # Verify that the not equal (!=) operator works correctly
            [
                [(x, y, operator.ne) for j, y in enumerate(SPECIFIERS) if i != j]
                for i, x in enumerate(SPECIFIERS)
            ]
        ),
    )
    def test_comparison_true(self, left, right, op):
        assert op(SpecifierSet(left), SpecifierSet(right))
        assert op(SpecifierSet(left), Specifier(right))
        assert op(Specifier(left), SpecifierSet(right))
        assert op(left, SpecifierSet(right))
        assert op(SpecifierSet(left), right)

    @pytest.mark.parametrize(
        ("left", "right", "op"),
        itertools.chain.from_iterable(
            # Verify that the equal (==) operator works correctly
            [[(x, x, operator.ne) for x in SPECIFIERS]]
            +
            # Verify that the not equal (!=) operator works correctly
            [
                [(x, y, operator.eq) for j, y in enumerate(SPECIFIERS) if i != j]
                for i, x in enumerate(SPECIFIERS)
            ]
        ),
    )
    def test_comparison_false(self, left, right, op):
        assert not op(SpecifierSet(left), SpecifierSet(right))
        assert not op(SpecifierSet(left), Specifier(right))
        assert not op(Specifier(left), SpecifierSet(right))
        assert not op(left, SpecifierSet(right))
        assert not op(SpecifierSet(left), right)

    @pytest.mark.parametrize(("left", "right"), [("==2.8.0", "==2.8")])
    def test_comparison_canonicalizes(self, left, right):
        assert SpecifierSet(left) == SpecifierSet(right)
        assert left == SpecifierSet(right)
        assert SpecifierSet(left) == right

    def test_comparison_non_specifier(self):
        assert SpecifierSet("==1.0") != 12
        assert not SpecifierSet("==1.0") == 12

    @pytest.mark.parametrize(
        ("version", "specifier", "expected"),
        [
            ("1.0.0+local", "==1.0.0", True),
            ("1.0.0+local", "!=1.0.0", False),
            ("1.0.0+local", "<=1.0.0", True),
            ("1.0.0+local", ">=1.0.0", True),
            ("1.0.0+local", "<1.0.0", False),
            ("1.0.0+local", ">1.0.0", False),
        ],
    )
    def test_comparison_ignores_local(self, version, specifier, expected):
        assert (Version(version) in SpecifierSet(specifier)) == expected

    def test_contains_with_compatible_operator(self):
        combination = SpecifierSet("~=1.18.0") & SpecifierSet("~=1.18")
        assert "1.19.5" not in combination
        assert "1.18.0" in combination

    @pytest.mark.parametrize(
        ("spec1", "spec2", "input_versions"),
        [
            # Test zero padding
            ("===1.0", "===1.0.0", ["1.0", "1.0.0"]),
            ("===1.0.0", "===1.0", ["1.0", "1.0.0"]),
            ("===1.0", "===1.0.0", ["1.0.0", "1.0"]),
            ("===1.0.0", "===1.0", ["1.0.0", "1.0"]),
            # Test local versions
            ("===1.0", "===1.0+local", ["1.0", "1.0+local"]),
            ("===1.0+local", "===1.0", ["1.0", "1.0+local"]),
            ("===1.0", "===1.0+local", ["1.0+local", "1.0"]),
            ("===1.0+local", "===1.0", ["1.0+local", "1.0"]),
        ],
    )
    def test_arbitrary_equality_is_intersection_preserving(
        self, spec1, spec2, input_versions
    ):
        """
        In general we expect for two specifiers s1 and s2, that the two statements
        are equivalent:
         * set((s1, s2).filter(versions))
         * set(s1.filter(versions)) & set(s2.filter(versions)).

        This is tricky with the arbitrary equality operator (===) since it does
        not follow normal version comparison rules.
        """
        s1 = Specifier(spec1)
        s2 = Specifier(spec2)
        versions1 = set(s1.filter(input_versions))
        versions2 = set(s2.filter(input_versions))
        combined_versions = set(SpecifierSet(f"{spec1},{spec2}").filter(input_versions))

        assert versions1 & versions2 == combined_versions
