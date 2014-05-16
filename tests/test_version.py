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

import pretend
import pytest

from packaging.version import Version, InvalidVersion


# This list must be in the correct sorting order
VERSIONS = [
    # Implicit epoch of 0
    "1.0.dev456", "1.0a1", "1.0a2.dev456", "1.0a12.dev456", "1.0a12",
    "1.0b1.dev456", "1.0b2", "1.0b2.post345.dev456", "1.0b2.post345",
    "1.0c1.dev456", "1.0c1", "1.0rc2", "1.0c3", "1.0", "1.0.post456.dev34",
    "1.0.post456", "1.1.dev1", "1.2+123abc", "1.2+123abc456", "1.2+abc",
    "1.2+abc123", "1.2+abc123def", "1.2+1234.abc", "1.2+123456",

    # Explicit epoch of 1
    "1:1.0.dev456", "1:1.0a1", "1:1.0a2.dev456", "1:1.0a12.dev456", "1:1.0a12",
    "1:1.0b1.dev456", "1:1.0b2", "1:1.0b2.post345.dev456", "1:1.0b2.post345",
    "1:1.0c1.dev456", "1:1.0c1", "1:1.0rc2", "1:1.0c3", "1:1.0",
    "1:1.0.post456.dev34", "1:1.0.post456", "1:1.1.dev1", "1:1.2+123abc",
    "1:1.2+123abc456", "1:1.2+abc", "1:1.2+abc123", "1:1.2+abc123def",
    "1:1.2+1234.abc", "1:1.2+123456",
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
            "1.0+A",
            "1.0+a+",
            "1.0++",
            "1.0+_foobar",
            "1.0+foo&asd",
            "1.0+1+1",
            "1.0+1_1",
        ]
    )
    def test_invalid_versions(self, version):
        with pytest.raises(InvalidVersion):
            Version(version)

    @pytest.mark.parametrize(
        ("version", "expected"),
        [
            ("1.0.dev456", "1.dev456"),
            ("1.0a1", "1a1"),
            ("1.0a2.dev456", "1a2.dev456"),
            ("1.0a12.dev456", "1a12.dev456"),
            ("1.0a12", "1a12"),
            ("1.0b1.dev456", "1b1.dev456"),
            ("1.0b2", "1b2"),
            ("1.0b2.post345.dev456", "1b2.post345.dev456"),
            ("1.0b2.post345", "1b2.post345"),
            ("1.0c1.dev456", "1c1.dev456"),
            ("1.0c1", "1c1"),
            ("1.0", "1"),
            ("1.0.post456.dev34", "1.post456.dev34"),
            ("1.0.post456", "1.post456"),
            ("1.0.1", "1.0.1"),
            ("0:1.0.2", "1.0.2"),
            ("1.0.3+7", "1.0.3+7"),
            ("0:1.0.4+8.0", "1.0.4+8.0"),
            ("1.0.5+9.5", "1.0.5+9.5"),
            ("1.2+1234.abc", "1.2+1234.abc"),
            ("1.2+123456", "1.2+123456"),
            ("1.2+123abc", "1.2+123abc"),
            ("1.2+123abc456", "1.2+123abc456"),
            ("1.2+abc", "1.2+abc"),
            ("1.2+abc123", "1.2+abc123"),
            ("1.2+abc123def", "1.2+abc123def"),
            ("1.1.dev1", "1.1.dev1"),
            ("7:1.0.dev456", "7:1.dev456"),
            ("7:1.0a1", "7:1a1"),
            ("7:1.0a2.dev456", "7:1a2.dev456"),
            ("7:1.0a12.dev456", "7:1a12.dev456"),
            ("7:1.0a12", "7:1a12"),
            ("7:1.0b1.dev456", "7:1b1.dev456"),
            ("7:1.0b2", "7:1b2"),
            ("7:1.0b2.post345.dev456", "7:1b2.post345.dev456"),
            ("7:1.0b2.post345", "7:1b2.post345"),
            ("7:1.0c1.dev456", "7:1c1.dev456"),
            ("7:1.0c1", "7:1c1"),
            ("7:1.0", "7:1"),
            ("7:1.0.post456.dev34", "7:1.post456.dev34"),
            ("7:1.0.post456", "7:1.post456"),
            ("7:1.0.1", "7:1.0.1"),
            ("7:1.0.2", "7:1.0.2"),
            ("7:1.0.3+7", "7:1.0.3+7"),
            ("7:1.0.4+8.0", "7:1.0.4+8.0"),
            ("7:1.0.5+9.5", "7:1.0.5+9.5"),
            ("7:1.1.dev1", "7:1.1.dev1"),
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
            ("1.0", "1"),
            ("1.0.dev6", "1.dev6"),
            ("1.0a1", "1a1"),
            ("1.0a1.post5", "1a1.post5"),
            ("1.0a1.post5.dev6", "1a1.post5.dev6"),
            ("1.0rc4", "1c4"),
            ("1.0.post5", "1.post5"),
            ("1:1.0", "1:1"),
            ("1:1.0.dev6", "1:1.dev6"),
            ("1:1.0a1", "1:1a1"),
            ("1:1.0a1.post5", "1:1a1.post5"),
            ("1:1.0a1.post5.dev6", "1:1a1.post5.dev6"),
            ("1:1.0rc4", "1:1c4"),
            ("1:1.0.post5", "1:1.post5"),
            ("1.0+deadbeef", "1"),
            ("1.0.dev6+deadbeef", "1.dev6"),
            ("1.0a1+deadbeef", "1a1"),
            ("1.0a1.post5+deadbeef", "1a1.post5"),
            ("1.0a1.post5.dev6+deadbeef", "1a1.post5.dev6"),
            ("1.0rc4+deadbeef", "1c4"),
            ("1.0.post5+deadbeef", "1.post5"),
            ("1:1.0+deadbeef", "1:1"),
            ("1:1.0.dev6+deadbeef", "1:1.dev6"),
            ("1:1.0a1+deadbeef", "1:1a1"),
            ("1:1.0a1.post5+deadbeef", "1:1a1.post5"),
            ("1:1.0a1.post5.dev6+deadbeef", "1:1a1.post5.dev6"),
            ("1:1.0rc4+deadbeef", "1:1c4"),
            ("1:1.0.post5+deadbeef", "1:1.post5"),
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
            ("1:1.0", None),
            ("1:1.0.dev6", None),
            ("1:1.0a1", None),
            ("1:1.0a1.post5", None),
            ("1:1.0a1.post5.dev6", None),
            ("1:1.0rc4", None),
            ("1:1.0.post5", None),
            ("1.0+deadbeef", "deadbeef"),
            ("1.0.dev6+deadbeef", "deadbeef"),
            ("1.0a1+deadbeef", "deadbeef"),
            ("1.0a1.post5+deadbeef", "deadbeef"),
            ("1.0a1.post5.dev6+deadbeef", "deadbeef"),
            ("1.0rc4+deadbeef", "deadbeef"),
            ("1.0.post5+deadbeef", "deadbeef"),
            ("1:1.0+deadbeef", "deadbeef"),
            ("1:1.0.dev6+deadbeef", "deadbeef"),
            ("1:1.0a1+deadbeef", "deadbeef"),
            ("1:1.0a1.post5+deadbeef", "deadbeef"),
            ("1:1.0a1.post5.dev6+deadbeef", "deadbeef"),
            ("1:1.0rc4+deadbeef", "deadbeef"),
            ("1:1.0.post5+deadbeef", "deadbeef"),
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
