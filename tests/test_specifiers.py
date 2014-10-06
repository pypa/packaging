# Copyright 2014 Donald Stufft
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from __future__ import absolute_import, division, print_function

import itertools
import operator
import re

import pytest

from packaging.specifiers import InvalidSpecifier, Specifier
from packaging.version import Version

from .test_version import VERSIONS, LEGACY_VERSIONS


# These should all be without spaces, we'll generate some with spaces using
# these as templates.
SPECIFIERS = [
    "~=2.0", "==2.1.*", "==2.1.0.3", "!=2.2.*", "!=2.2.0.5", "<=5", ">=7.9a1",
    "<1.0.dev1", ">2.0.post1", "===lolwat",
]


class TestSpecifier:

    @pytest.mark.parametrize(
        "specifier",
        # Generate all possible combinations of the SPECIFIERS to test to make
        # sure they all work.
        [
            ",".join(combination)
            for combination in itertools.chain(*(
                itertools.combinations(SPECIFIERS, n)
                for n in range(1, len(SPECIFIERS) + 1)
            ))
        ]
        +
        # Do the same thing, except include spaces in the specifiers
        [
            ",".join([
                " ".join(re.split(r"(===|~=|==|!=|<=|>=|<|>)", item)[1:])
                for item in combination
            ])
            for combination in itertools.chain(*(
                itertools.combinations(SPECIFIERS, n)
                for n in range(1, len(SPECIFIERS) + 1)
            ))
        ]
        +
        # Finally do the same thing once more, except join some with spaces and
        # some without.
        [
            ",".join([
                ("" if j % 2 else " ").join(
                    re.split(r"(===|~=|==|!=|<=|>=|<|>)", item)[1:]
                )
                for j, item in enumerate(combination)
            ])
            for combination in itertools.chain(*(
                itertools.combinations(SPECIFIERS, n)
                for n in range(1, len(SPECIFIERS) + 1)
            ))
        ]
    )
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

            # Prefix matching cannot be used inside of a local version
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
            "1.0dev",
            "1.0-dev",
            "1.0-dev1",
            "1.0DEV",
            "1.0.DEV",
            "1.0DEV1",
            "1.0DEV",
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
            "1.0post",
            "1.0-post",
            "1.0-post1",
            "1.0POST",
            "1.0.POST",
            "1.0POST1",
            "1.0POST",
            "1.0.POST1",
            "1.0-POST",
            "1.0-POST1",
            "1.0-5",

            # Local version case insensitivity
            "1.0+AbC"

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

            # Multiple item specifiers should be sorted lexicographically
            ("<2,!=1.5", "!=1.5,<2"),
            (
                "~=1.3.5,>5.3,==1.3.*,<=700,>=0,!=99.99,<1000",
                "!=99.99,<1000,<=700,==1.3.*,>5.3,>=0,~=1.3.5",
            ),

            # Spaces should be removed
            ("== 2.0", "==2.0"),
            (">=2.0, !=2.1.0", "!=2.1.0,>=2.0"),
            ("< 2, >= 5,~= 2.2,==5.4", "<2,==5.4,>=5,~=2.2"),
        ],
    )
    def test_specifiers_str_and_repr(self, specifier, expected):
        spec = Specifier(specifier)

        assert str(spec) == expected
        assert repr(spec) == "<Specifier({0})>".format(repr(expected))

    @pytest.mark.parametrize("specifier", SPECIFIERS)
    def test_specifiers_hash(self, specifier):
        assert hash(Specifier(specifier)) == hash(Specifier(specifier))

    @pytest.mark.parametrize(
        "specifiers",
        [
            ["!=2", "==2.*"],
            [">=5.7", "<7000"],
            ["==2.5.0+3", ">1"],
        ],
    )
    def test_combining_specifiers(self, specifiers):
        # Test combining Specifier objects
        spec = Specifier(specifiers[0])
        for s in specifiers[1:]:
            spec &= Specifier(s)
        assert spec == Specifier(",".join(specifiers))

        # Test combining a string with a Specifier object
        spec = Specifier(specifiers[0])
        for s in specifiers[1:]:
            spec &= s
        assert spec == Specifier(",".join(specifiers))

    def test_combining_non_specifiers(self):
        with pytest.raises(TypeError):
            Specifier("==2.0") & 12

    @pytest.mark.parametrize(
        ("left", "right", "op"),
        itertools.chain(
            *
            # Verify that the equal (==) operator works correctly
            [
                [(x, x, operator.eq) for x in SPECIFIERS]
            ]
            +
            # Verify that the not equal (!=) operator works correctly
            [
                [
                    (x, y, operator.ne)
                    for j, y in enumerate(SPECIFIERS)
                    if i != j
                ]
                for i, x in enumerate(SPECIFIERS)
            ]
        )
    )
    def test_comparison_true(self, left, right, op):
        assert op(Specifier(left), Specifier(right))
        assert op(left, Specifier(right))
        assert op(Specifier(left), right)

    @pytest.mark.parametrize(
        ("left", "right", "op"),
        itertools.chain(
            *
            # Verify that the equal (==) operator works correctly
            [
                [(x, x, operator.ne) for x in SPECIFIERS]
            ]
            +
            # Verify that the not equal (!=) operator works correctly
            [
                [
                    (x, y, operator.eq)
                    for j, y in enumerate(SPECIFIERS)
                    if i != j
                ]
                for i, x in enumerate(SPECIFIERS)
            ]
        )
    )
    def test_comparison_false(self, left, right, op):
        assert not op(Specifier(left), Specifier(right))
        assert not op(left, Specifier(right))
        assert not op(Specifier(left), right)

    def test_comparison_non_specifier(self):
        assert Specifier("==1.0") != 12
        assert not Specifier("==1.0") == 12

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
                ("2rc1", "==2.*"),
                ("2", "==2.*"),
                ("2.0", "==2.*"),
                ("2.0.0", "==2.*"),
                ("2.0.post1", "==2.0.post1.*"),
                ("2.0.post1.dev1", "==2.0.post1.*"),

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

                # Test the greater than operation
                ("3", ">2"),
                ("2.1", ">2.0"),

                # Test the less than operation
                ("1", "<2"),
                ("2.0", "<2.1"),

                # Test the compatibility operation
                ("1", "~=1.0"),
                ("1.0.1", "~=1.0"),
                ("1.1", "~=1.0"),
                ("1.9999999", "~=1.0"),

                # Test that epochs are handled sanely
                ("2!1.0", "~=2!1.0"),
                ("2!1.0", "==2!1.*"),
                ("2!1.0", "==2!1.0"),
                ("2!1.0", "!=1.0"),
                ("1.0", "!=2!1.0"),
                ("1.0", "<=2!0.1"),
                ("2!1.0", ">=2.0"),
                ("1.0", "<2!0.1"),
                ("2!1.0", ">2.0"),
            ]
        ]
        +
        [
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
                ("2rc1", "!=2.*"),
                ("2", "!=2.*"),
                ("2.0", "!=2.*"),
                ("2.0.0", "!=2.*"),
                ("2.0.post1", "!=2.0.post1.*"),
                ("2.0.post1.dev1", "!=2.0.post1.*"),

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
                ("2.0.1", ">2"),

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
            assert spec.contains(version)

            # Test that the version instance form works
            assert spec.contains(Version(version))
        else:
            # Test that the plain string form works
            assert not spec.contains(version)

            # Test that the version instance form works
            assert not spec.contains(Version(version))

    @pytest.mark.parametrize(
        ("version", "spec", "expected"),
        [
            # Test identity comparison by itself
            ("lolwat", "===lolwat", True),
            ("Lolwat", "===lolwat", True),
            ("1.0", "===1.0", True),
            ("nope", "===lolwat", False),
            ("1.0.0", "===1.0", False),

            # Test multiple specs combined with an identity comparison
            ("nope", "===nope,!=1.0", False),
            ("1.0.0", "===1.0.0,==1.*", True),
            ("1.0.0", "===1.0,==1.*", False),
        ],
    )
    def test_specifiers_identity(self, version, spec, expected):
        spec = Specifier(spec)

        if expected:
            # Identity comparisons only support the plain string form
            assert spec.contains(version)
        else:
            # Identity comparisons only support the plain string form
            assert not spec.contains(version)

    @pytest.mark.parametrize(
        "version",
        VERSIONS + LEGACY_VERSIONS,
    )
    def test_empty_specifier(self, version):
        spec = Specifier(prereleases=True)

        assert spec.contains(version)

    @pytest.mark.parametrize(
        ("specifier", "expected"),
        [
            ("==1.0", False),
            ("", False),
            (">=1.0", False),
            ("<=1.0", False),
            ("~=1.0", False),
            ("<1.0", False),
            (">1.0", False),
            ("<1.0.dev1", False),
            (">1.0.dev1", False),
            ("==1.0.*", False),
            ("==1.0.dev1", True),
            (">=1.0.dev1", True),
            ("<=1.0.dev1", True),
            ("~=1.0.dev1", True),
        ],
    )
    def test_specifier_prereleases_detection(self, specifier, expected):
        assert Specifier(specifier).prereleases == expected

    def test_specifier_prereleases_explicit(self):
        spec = Specifier()
        assert not spec.prereleases
        assert not spec.contains("1.0.dev1")
        spec.prereleases = True
        assert spec.prereleases
        assert spec.contains("1.0.dev1")

        spec = Specifier(prereleases=True)
        assert spec.prereleases
        assert spec.contains("1.0.dev1")
        spec.prereleases = False
        assert not spec.prereleases
        assert not spec.contains("1.0.dev1")

        spec = Specifier(prereleases=True)
        assert spec.prereleases
        assert spec.contains("1.0.dev1")
        spec.prereleases = None
        assert not spec.prereleases
        assert not spec.contains("1.0.dev1")

    @pytest.mark.parametrize(
        ("specifier", "version", "expected"),
        [
            (">=1.0", "2.0.dev1", False),
            (">=2.0.dev1", "2.0a1", True),
            ("==2.0.*", "2.0a1.dev1", False),
            ("==2.0a1.*", "2.0a1.dev1", True),
            ("<=2.0", "1.0.dev1", False),
            ("<=2.0.dev1", "1.0a1", True),
        ],
    )
    def test_specifiers_prereleases(self, specifier, version, expected):
        spec = Specifier(specifier)

        if expected:
            assert spec.contains(version)
            spec.prereleases = False
            assert not spec.contains(version)
        else:
            assert not spec.contains(version)
            spec.prereleases = True
            assert spec.contains(version)

    @pytest.mark.parametrize(
        ("specifier", "prereleases", "input", "expected"),
        [
            ("", None, ["1.0", "2.0a1"], ["1.0"]),
            (">=1.0.dev1", None, ["1.0", "2.0a1"], ["1.0", "2.0a1"]),
            ("", None, ["1.0a1"], ["1.0a1"]),
            ("", False, ["1.0a1"], []),
            (">=1.0.dev1", False, ["1.0", "2.0a1"], ["1.0"]),
            ("", True, ["1.0", "2.0a1"], ["1.0", "2.0a1"]),
            ("", None, ["1.0", Version("2.0")], ["1.0", Version("2.0")]),
        ],
    )
    def test_specifier_filter(self, specifier, prereleases, input, expected):
        spec = Specifier(specifier)

        kwargs = (
            {"prereleases": prereleases} if prereleases is not None else {}
        )

        assert list(spec.filter(input, **kwargs)) == expected
