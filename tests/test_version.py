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

import pretend
import pytest

from packaging.version import (
    Version, LegacyVersion, InvalidVersion, Specifier, InvalidSpecifier,
)


# This list must be in the correct sorting order
VERSIONS = [
    # Implicit epoch of 0
    "1.0.dev456", "1.0a1", "1.0a2.dev456", "1.0a12.dev456", "1.0a12",
    "1.0b1.dev456", "1.0b2", "1.0b2.post345.dev456", "1.0b2.post345",
    "1.0b2-346", "1.0c1.dev456", "1.0c1", "1.0rc2", "1.0c3", "1.0",
    "1.0.post456.dev34", "1.0.post456", "1.1.dev1", "1.2+123abc",
    "1.2+123abc456", "1.2+abc", "1.2+abc123", "1.2+abc123def", "1.2+1234.abc",
    "1.2+123456",

    # Explicit epoch of 1
    "1!1.0.dev456", "1!1.0a1", "1!1.0a2.dev456", "1!1.0a12.dev456", "1!1.0a12",
    "1!1.0b1.dev456", "1!1.0b2", "1!1.0b2.post345.dev456", "1!1.0b2.post345",
    "1!1.0b2-346", "1!1.0c1.dev456", "1!1.0c1", "1!1.0rc2", "1!1.0c3", "1!1.0",
    "1!1.0.post456.dev34", "1!1.0.post456", "1!1.1.dev1", "1!1.2+123abc",
    "1!1.2+123abc456", "1!1.2+abc", "1!1.2+abc123", "1!1.2+abc123def",
    "1!1.2+1234.abc", "1!1.2+123456",
]


class TestVersion:

    @pytest.mark.parametrize("version", VERSIONS)
    def test_valid_versions(self, version):
        Version(version)

    @pytest.mark.parametrize(
        "version",
        [
            # Non sensical versions should be invalid
            "french toast",

            # Versions with invalid local versions
            "1.0+a+",
            "1.0++",
            "1.0+_foobar",
            "1.0+foo&asd",
            "1.0+1+1",
        ]
    )
    def test_invalid_versions(self, version):
        with pytest.raises(InvalidVersion):
            Version(version)

    @pytest.mark.parametrize(
        ("version", "normalized"),
        [
            # Various development release incarnations
            ("1.0dev", "1.0.dev0"),
            ("1.0.dev", "1.0.dev0"),
            ("1.0dev1", "1.0.dev1"),
            ("1.0dev", "1.0.dev0"),
            ("1.0-dev", "1.0.dev0"),
            ("1.0-dev1", "1.0.dev1"),
            ("1.0DEV", "1.0.dev0"),
            ("1.0.DEV", "1.0.dev0"),
            ("1.0DEV1", "1.0.dev1"),
            ("1.0DEV", "1.0.dev0"),
            ("1.0.DEV1", "1.0.dev1"),
            ("1.0-DEV", "1.0.dev0"),
            ("1.0-DEV1", "1.0.dev1"),

            # Various alpha incarnations
            ("1.0a", "1.0a0"),
            ("1.0.a", "1.0a0"),
            ("1.0.a1", "1.0a1"),
            ("1.0-a", "1.0a0"),
            ("1.0-a1", "1.0a1"),
            ("1.0alpha", "1.0a0"),
            ("1.0.alpha", "1.0a0"),
            ("1.0.alpha1", "1.0a1"),
            ("1.0-alpha", "1.0a0"),
            ("1.0-alpha1", "1.0a1"),
            ("1.0A", "1.0a0"),
            ("1.0.A", "1.0a0"),
            ("1.0.A1", "1.0a1"),
            ("1.0-A", "1.0a0"),
            ("1.0-A1", "1.0a1"),
            ("1.0ALPHA", "1.0a0"),
            ("1.0.ALPHA", "1.0a0"),
            ("1.0.ALPHA1", "1.0a1"),
            ("1.0-ALPHA", "1.0a0"),
            ("1.0-ALPHA1", "1.0a1"),

            # Various beta incarnations
            ("1.0b", "1.0b0"),
            ("1.0.b", "1.0b0"),
            ("1.0.b1", "1.0b1"),
            ("1.0-b", "1.0b0"),
            ("1.0-b1", "1.0b1"),
            ("1.0beta", "1.0b0"),
            ("1.0.beta", "1.0b0"),
            ("1.0.beta1", "1.0b1"),
            ("1.0-beta", "1.0b0"),
            ("1.0-beta1", "1.0b1"),
            ("1.0B", "1.0b0"),
            ("1.0.B", "1.0b0"),
            ("1.0.B1", "1.0b1"),
            ("1.0-B", "1.0b0"),
            ("1.0-B1", "1.0b1"),
            ("1.0BETA", "1.0b0"),
            ("1.0.BETA", "1.0b0"),
            ("1.0.BETA1", "1.0b1"),
            ("1.0-BETA", "1.0b0"),
            ("1.0-BETA1", "1.0b1"),

            # Various release candidate incarnations
            ("1.0c", "1.0c0"),
            ("1.0.c", "1.0c0"),
            ("1.0.c1", "1.0c1"),
            ("1.0-c", "1.0c0"),
            ("1.0-c1", "1.0c1"),
            ("1.0rc", "1.0c0"),
            ("1.0.rc", "1.0c0"),
            ("1.0.rc1", "1.0c1"),
            ("1.0-rc", "1.0c0"),
            ("1.0-rc1", "1.0c1"),
            ("1.0C", "1.0c0"),
            ("1.0.C", "1.0c0"),
            ("1.0.C1", "1.0c1"),
            ("1.0-C", "1.0c0"),
            ("1.0-C1", "1.0c1"),
            ("1.0RC", "1.0c0"),
            ("1.0.RC", "1.0c0"),
            ("1.0.RC1", "1.0c1"),
            ("1.0-RC", "1.0c0"),
            ("1.0-RC1", "1.0c1"),

            # Various post release incarnations
            ("1.0post", "1.0.post0"),
            ("1.0.post", "1.0.post0"),
            ("1.0post1", "1.0.post1"),
            ("1.0post", "1.0.post0"),
            ("1.0-post", "1.0.post0"),
            ("1.0-post1", "1.0.post1"),
            ("1.0POST", "1.0.post0"),
            ("1.0.POST", "1.0.post0"),
            ("1.0POST1", "1.0.post1"),
            ("1.0POST", "1.0.post0"),
            ("1.0.POST1", "1.0.post1"),
            ("1.0-POST", "1.0.post0"),
            ("1.0-POST1", "1.0.post1"),
            ("1.0-5", "1.0.post5"),

            # Local version case insensitivity
            ("1.0+AbC", "1.0+abc"),

            # Integer Normalization
            ("1.01", "1.1"),
            ("1.0a05", "1.0a5"),
            ("1.0b07", "1.0b7"),
            ("1.0c056", "1.0c56"),
            ("1.0rc09", "1.0c9"),
            ("1.0.post000", "1.0.post0"),
            ("1.1.dev09000", "1.1.dev9000"),
            ("00!1.2", "1.2"),
            ("0100!0.0", "100!0.0"),

            # Various other normalizations
            ("v1.0", "1.0"),
            ("   v1.0\t\n", "1.0"),
        ],
    )
    def test_normalized_versions(self, version, normalized):
        assert str(Version(version)) == normalized

    @pytest.mark.parametrize(
        ("version", "expected"),
        [
            ("1.0.dev456", "1.0.dev456"),
            ("1.0a1", "1.0a1"),
            ("1.0a2.dev456", "1.0a2.dev456"),
            ("1.0a12.dev456", "1.0a12.dev456"),
            ("1.0a12", "1.0a12"),
            ("1.0b1.dev456", "1.0b1.dev456"),
            ("1.0b2", "1.0b2"),
            ("1.0b2.post345.dev456", "1.0b2.post345.dev456"),
            ("1.0b2.post345", "1.0b2.post345"),
            ("1.0c1.dev456", "1.0c1.dev456"),
            ("1.0c1", "1.0c1"),
            ("1.0", "1.0"),
            ("1.0.post456.dev34", "1.0.post456.dev34"),
            ("1.0.post456", "1.0.post456"),
            ("1.0.1", "1.0.1"),
            ("0!1.0.2", "1.0.2"),
            ("1.0.3+7", "1.0.3+7"),
            ("0!1.0.4+8.0", "1.0.4+8.0"),
            ("1.0.5+9.5", "1.0.5+9.5"),
            ("1.2+1234.abc", "1.2+1234.abc"),
            ("1.2+123456", "1.2+123456"),
            ("1.2+123abc", "1.2+123abc"),
            ("1.2+123abc456", "1.2+123abc456"),
            ("1.2+abc", "1.2+abc"),
            ("1.2+abc123", "1.2+abc123"),
            ("1.2+abc123def", "1.2+abc123def"),
            ("1.1.dev1", "1.1.dev1"),
            ("7!1.0.dev456", "7!1.0.dev456"),
            ("7!1.0a1", "7!1.0a1"),
            ("7!1.0a2.dev456", "7!1.0a2.dev456"),
            ("7!1.0a12.dev456", "7!1.0a12.dev456"),
            ("7!1.0a12", "7!1.0a12"),
            ("7!1.0b1.dev456", "7!1.0b1.dev456"),
            ("7!1.0b2", "7!1.0b2"),
            ("7!1.0b2.post345.dev456", "7!1.0b2.post345.dev456"),
            ("7!1.0b2.post345", "7!1.0b2.post345"),
            ("7!1.0c1.dev456", "7!1.0c1.dev456"),
            ("7!1.0c1", "7!1.0c1"),
            ("7!1.0", "7!1.0"),
            ("7!1.0.post456.dev34", "7!1.0.post456.dev34"),
            ("7!1.0.post456", "7!1.0.post456"),
            ("7!1.0.1", "7!1.0.1"),
            ("7!1.0.2", "7!1.0.2"),
            ("7!1.0.3+7", "7!1.0.3+7"),
            ("7!1.0.4+8.0", "7!1.0.4+8.0"),
            ("7!1.0.5+9.5", "7!1.0.5+9.5"),
            ("7!1.1.dev1", "7!1.1.dev1"),
        ],
    )
    def test_version_str_repr(self, version, expected):
        assert str(Version(version)) == expected
        assert (repr(Version(version))
                == "<Version({0})>".format(repr(expected)))

    def test_version_rc_and_c_equals(self):
        assert Version("1.0rc1") == Version("1.0c1")

    @pytest.mark.parametrize("version", VERSIONS)
    def test_version_hash(self, version):
        assert hash(Version(version)) == hash(Version(version))

    @pytest.mark.parametrize(
        ("version", "public"),
        [
            ("1.0", "1.0"),
            ("1.0.dev6", "1.0.dev6"),
            ("1.0a1", "1.0a1"),
            ("1.0a1.post5", "1.0a1.post5"),
            ("1.0a1.post5.dev6", "1.0a1.post5.dev6"),
            ("1.0rc4", "1.0c4"),
            ("1.0.post5", "1.0.post5"),
            ("1!1.0", "1!1.0"),
            ("1!1.0.dev6", "1!1.0.dev6"),
            ("1!1.0a1", "1!1.0a1"),
            ("1!1.0a1.post5", "1!1.0a1.post5"),
            ("1!1.0a1.post5.dev6", "1!1.0a1.post5.dev6"),
            ("1!1.0rc4", "1!1.0c4"),
            ("1!1.0.post5", "1!1.0.post5"),
            ("1.0+deadbeef", "1.0"),
            ("1.0.dev6+deadbeef", "1.0.dev6"),
            ("1.0a1+deadbeef", "1.0a1"),
            ("1.0a1.post5+deadbeef", "1.0a1.post5"),
            ("1.0a1.post5.dev6+deadbeef", "1.0a1.post5.dev6"),
            ("1.0rc4+deadbeef", "1.0c4"),
            ("1.0.post5+deadbeef", "1.0.post5"),
            ("1!1.0+deadbeef", "1!1.0"),
            ("1!1.0.dev6+deadbeef", "1!1.0.dev6"),
            ("1!1.0a1+deadbeef", "1!1.0a1"),
            ("1!1.0a1.post5+deadbeef", "1!1.0a1.post5"),
            ("1!1.0a1.post5.dev6+deadbeef", "1!1.0a1.post5.dev6"),
            ("1!1.0rc4+deadbeef", "1!1.0c4"),
            ("1!1.0.post5+deadbeef", "1!1.0.post5"),
        ],
    )
    def test_version_public(self, version, public):
        assert Version(version).public == public

    @pytest.mark.parametrize(
        ("version", "local"),
        [
            ("1.0", None),
            ("1.0.dev6", None),
            ("1.0a1", None),
            ("1.0a1.post5", None),
            ("1.0a1.post5.dev6", None),
            ("1.0rc4", None),
            ("1.0.post5", None),
            ("1!1.0", None),
            ("1!1.0.dev6", None),
            ("1!1.0a1", None),
            ("1!1.0a1.post5", None),
            ("1!1.0a1.post5.dev6", None),
            ("1!1.0rc4", None),
            ("1!1.0.post5", None),
            ("1.0+deadbeef", "deadbeef"),
            ("1.0.dev6+deadbeef", "deadbeef"),
            ("1.0a1+deadbeef", "deadbeef"),
            ("1.0a1.post5+deadbeef", "deadbeef"),
            ("1.0a1.post5.dev6+deadbeef", "deadbeef"),
            ("1.0rc4+deadbeef", "deadbeef"),
            ("1.0.post5+deadbeef", "deadbeef"),
            ("1!1.0+deadbeef", "deadbeef"),
            ("1!1.0.dev6+deadbeef", "deadbeef"),
            ("1!1.0a1+deadbeef", "deadbeef"),
            ("1!1.0a1.post5+deadbeef", "deadbeef"),
            ("1!1.0a1.post5.dev6+deadbeef", "deadbeef"),
            ("1!1.0rc4+deadbeef", "deadbeef"),
            ("1!1.0.post5+deadbeef", "deadbeef"),
        ],
    )
    def test_version_local(self, version, local):
        assert Version(version).local == local

    @pytest.mark.parametrize(
        ("version", "expected"),
        [
            ("1.0.dev1", True),
            ("1.0a1.dev1", True),
            ("1.0b1.dev1", True),
            ("1.0c1.dev1", True),
            ("1.0rc1.dev1", True),
            ("1.0a1", True),
            ("1.0b1", True),
            ("1.0c1", True),
            ("1.0rc1", True),
            ("1.0a1.post1.dev1", True),
            ("1.0b1.post1.dev1", True),
            ("1.0c1.post1.dev1", True),
            ("1.0rc1.post1.dev1", True),
            ("1.0a1.post1", True),
            ("1.0b1.post1", True),
            ("1.0c1.post1", True),
            ("1.0rc1.post1", True),
            ("1.0", False),
            ("1.0+dev", False),
            ("1.0.post1", False),
            ("1.0.post1+dev", False),
        ],
    )
    def test_version_is_prerelease(self, version, expected):
        assert Version(version).is_prerelease is expected

    @pytest.mark.parametrize(
        ("left", "right", "op"),
        # Below we'll generate every possible combination of VERSIONS that
        # should be True for the given operator
        itertools.chain(
            *
            # Verify that the less than (<) operator works correctly
            [
                [(x, y, operator.lt) for y in VERSIONS[i + 1:]]
                for i, x in enumerate(VERSIONS)
            ]
            +
            # Verify that the less than equal (<=) operator works correctly
            [
                [(x, y, operator.le) for y in VERSIONS[i:]]
                for i, x in enumerate(VERSIONS)
            ]
            +
            # Verify that the equal (==) operator works correctly
            [
                [(x, x, operator.eq) for x in VERSIONS]
            ]
            +
            # Verify that the not equal (!=) operator works correctly
            [
                [(x, y, operator.ne) for j, y in enumerate(VERSIONS) if i != j]
                for i, x in enumerate(VERSIONS)
            ]
            +
            # Verify that the greater than equal (>=) operator works correctly
            [
                [(x, y, operator.ge) for y in VERSIONS[:i + 1]]
                for i, x in enumerate(VERSIONS)
            ]
            +
            # Verify that the greater than (>) operator works correctly
            [
                [(x, y, operator.gt) for y in VERSIONS[:i]]
                for i, x in enumerate(VERSIONS)
            ]
        )
    )
    def test_comparison_true(self, left, right, op):
        assert op(Version(left), Version(right))

    @pytest.mark.parametrize(
        ("left", "right", "op"),
        # Below we'll generate every possible combination of VERSIONS that
        # should be False for the given operator
        itertools.chain(
            *
            # Verify that the less than (<) operator works correctly
            [
                [(x, y, operator.lt) for y in VERSIONS[:i + 1]]
                for i, x in enumerate(VERSIONS)
            ]
            +
            # Verify that the less than equal (<=) operator works correctly
            [
                [(x, y, operator.le) for y in VERSIONS[:i]]
                for i, x in enumerate(VERSIONS)
            ]
            +
            # Verify that the equal (==) operator works correctly
            [
                [(x, y, operator.eq) for j, y in enumerate(VERSIONS) if i != j]
                for i, x in enumerate(VERSIONS)
            ]
            +
            # Verify that the not equal (!=) operator works correctly
            [
                [(x, x, operator.ne) for x in VERSIONS]
            ]
            +
            # Verify that the greater than equal (>=) operator works correctly
            [
                [(x, y, operator.ge) for y in VERSIONS[i + 1:]]
                for i, x in enumerate(VERSIONS)
            ]
            +
            # Verify that the greater than (>) operator works correctly
            [
                [(x, y, operator.gt) for y in VERSIONS[i:]]
                for i, x in enumerate(VERSIONS)
            ]
        )
    )
    def test_comparison_false(self, left, right, op):
        assert not op(Version(left), Version(right))

    @pytest.mark.parametrize(("op", "expected"), [("eq", False), ("ne", True)])
    def test_compare_other(self, op, expected):
        other = pretend.stub(
            **{"__{0}__".format(op): lambda other: NotImplemented}
        )

        assert getattr(operator, op)(Version("1"), other) is expected


LEGACY_VERSIONS = ["foobar", "a cat is fine too", "lolwut", "1-0"]


class TestLegacyVersion:

    @pytest.mark.parametrize("version", VERSIONS + LEGACY_VERSIONS)
    def test_valid_legacy_versions(self, version):
        LegacyVersion(version)

    @pytest.mark.parametrize("version", VERSIONS + LEGACY_VERSIONS)
    def test_legacy_version_str_repr(self, version):
        assert str(LegacyVersion(version)) == version
        assert (repr(LegacyVersion(version))
                == "<LegacyVersion({0})>".format(repr(version)))

    @pytest.mark.parametrize("version", VERSIONS + LEGACY_VERSIONS)
    def test_legacy_version_hash(self, version):
        assert hash(LegacyVersion(version)) == hash(LegacyVersion(version))

    @pytest.mark.parametrize("version", VERSIONS + LEGACY_VERSIONS)
    def test_legacy_version_public(self, version):
        assert LegacyVersion(version).public == version

    @pytest.mark.parametrize("version", VERSIONS + LEGACY_VERSIONS)
    def test_legacy_version_local(self, version):
        assert LegacyVersion(version).local is None

    @pytest.mark.parametrize("version", VERSIONS + LEGACY_VERSIONS)
    def test_legacy_version_is_prerelease(self, version):
        assert not LegacyVersion(version).is_prerelease

    @pytest.mark.parametrize(
        ("left", "right", "op"),
        # Below we'll generate every possible combination of
        # VERSIONS + LEGACY_VERSIONS that should be True for the given operator
        itertools.chain(
            *
            # Verify that the equal (==) operator works correctly
            [
                [(x, x, operator.eq) for x in VERSIONS + LEGACY_VERSIONS]
            ]
            +
            # Verify that the not equal (!=) operator works correctly
            [
                [
                    (x, y, operator.ne)
                    for j, y in enumerate(VERSIONS + LEGACY_VERSIONS)
                    if i != j
                ]
                for i, x in enumerate(VERSIONS + LEGACY_VERSIONS)
            ]
        )
    )
    def test_comparison_true(self, left, right, op):
        assert op(LegacyVersion(left), LegacyVersion(right))

    @pytest.mark.parametrize(
        ("left", "right", "op"),
        # Below we'll generate every possible combination of
        # VERSIONS + LEGACY_VERSIONS that should be False for the given
        # operator
        itertools.chain(
            *
            # Verify that the equal (==) operator works correctly
            [
                [
                    (x, y, operator.eq)
                    for j, y in enumerate(VERSIONS + LEGACY_VERSIONS)
                    if i != j
                ]
                for i, x in enumerate(VERSIONS + LEGACY_VERSIONS)
            ]
            +
            # Verify that the not equal (!=) operator works correctly
            [
                [(x, x, operator.ne) for x in VERSIONS + LEGACY_VERSIONS]
            ]
        )
    )
    def test_comparison_false(self, left, right, op):
        assert not op(LegacyVersion(left), LegacyVersion(right))

    @pytest.mark.parametrize(("op", "expected"), [("eq", False), ("ne", True)])
    def test_compare_other(self, op, expected):
        other = pretend.stub(
            **{"__{0}__".format(op): lambda other: NotImplemented}
        )

        assert getattr(operator, op)(LegacyVersion("1"), other) is expected


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
        spec = Specifier(spec)

        if expected:
            # Test that the plain string form works
            assert version in spec

            # Test that the version instance form works
            assert Version(version) in spec
        else:
            # Test that the plain string form works
            assert version not in spec

            # Test that the version instance form works
            assert Version(version) not in spec

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
            assert version in spec
        else:
            # Identity comparisons only support the plain string form
            assert version not in spec
