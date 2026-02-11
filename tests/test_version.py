# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.

from __future__ import annotations

import itertools
import operator
import sys
import typing

import pretend
import pytest

from packaging.version import InvalidVersion, Version, _VersionReplace, parse

if typing.TYPE_CHECKING:
    from collections.abc import Callable

    from typing_extensions import Self, Unpack

if sys.version_info >= (3, 13):
    from copy import replace
else:
    T = typing.TypeVar("T")

    class SupportsReplace(typing.Protocol):
        def __replace__(self, **kwargs: Unpack[_VersionReplace]) -> Self: ...

    S = typing.TypeVar("S", bound="SupportsReplace")

    def replace(item: S, **kwargs: Unpack[_VersionReplace]) -> S:
        return item.__replace__(**kwargs)


def test_parse() -> None:
    assert isinstance(parse("1.0"), Version)


def test_parse_raises() -> None:
    with pytest.raises(InvalidVersion):
        parse("lolwat")


# This list must be in the correct sorting order
VERSIONS = [
    # Implicit epoch of 0
    "1.0.dev456",
    "1.0a1",
    "1.0a2.dev456",
    "1.0a12.dev456",
    "1.0a12",
    "1.0b1.dev456",
    "1.0b2",
    "1.0b2.post345.dev456",
    "1.0b2.post345",
    "1.0b2-346",
    "1.0c1.dev456",
    "1.0c1",
    "1.0rc2",
    "1.0c3",
    "1.0",
    "1.0.post456.dev34",
    "1.0.post456",
    "1.1.dev1",
    "1.2+123abc",
    "1.2+123abc456",
    "1.2+abc",
    "1.2+abc123",
    "1.2+abc123def",
    "1.2+1234.abc",
    "1.2+123456",
    "1.2.r32+123456",
    "1.2.rev33+123456",
    # Explicit epoch of 1
    "1!1.0.dev456",
    "1!1.0a1",
    "1!1.0a2.dev456",
    "1!1.0a12.dev456",
    "1!1.0a12",
    "1!1.0b1.dev456",
    "1!1.0b2",
    "1!1.0b2.post345.dev456",
    "1!1.0b2.post345",
    "1!1.0b2-346",
    "1!1.0c1.dev456",
    "1!1.0c1",
    "1!1.0rc2",
    "1!1.0c3",
    "1!1.0",
    "1!1.0.post456.dev34",
    "1!1.0.post456",
    "1!1.1.dev1",
    "1!1.2+123abc",
    "1!1.2+123abc456",
    "1!1.2+abc",
    "1!1.2+abc123",
    "1!1.2+abc123def",
    "1!1.2+1234.abc",
    "1!1.2+123456",
    "1!1.2.r32+123456",
    "1!1.2.rev33+123456",
]


class TestVersion:
    @pytest.mark.parametrize("version", VERSIONS)
    def test_valid_versions(self, version: str) -> None:
        Version(version)

    def test_match_args(self) -> None:
        assert Version.__match_args__ == ("_str",)
        assert Version("1.2")._str == "1.2"

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
        ],
    )
    def test_invalid_versions(self, version: str) -> None:
        with pytest.raises(InvalidVersion):
            Version(version)

    @pytest.mark.parametrize(
        ("version", "normalized"),
        [
            # Various development release incarnations
            ("1.0dev", "1.0.dev0"),
            ("1.0.dev", "1.0.dev0"),
            ("1.0dev1", "1.0.dev1"),
            ("1.0-dev", "1.0.dev0"),
            ("1.0-dev1", "1.0.dev1"),
            ("1.0DEV", "1.0.dev0"),
            ("1.0.DEV", "1.0.dev0"),
            ("1.0DEV1", "1.0.dev1"),
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
            ("1.0c", "1.0rc0"),
            ("1.0.c", "1.0rc0"),
            ("1.0.c1", "1.0rc1"),
            ("1.0-c", "1.0rc0"),
            ("1.0-c1", "1.0rc1"),
            ("1.0rc", "1.0rc0"),
            ("1.0.rc", "1.0rc0"),
            ("1.0.rc1", "1.0rc1"),
            ("1.0-rc", "1.0rc0"),
            ("1.0-rc1", "1.0rc1"),
            ("1.0C", "1.0rc0"),
            ("1.0.C", "1.0rc0"),
            ("1.0.C1", "1.0rc1"),
            ("1.0-C", "1.0rc0"),
            ("1.0-C1", "1.0rc1"),
            ("1.0RC", "1.0rc0"),
            ("1.0.RC", "1.0rc0"),
            ("1.0.RC1", "1.0rc1"),
            ("1.0-RC", "1.0rc0"),
            ("1.0-RC1", "1.0rc1"),
            # Various post release incarnations
            ("1.0post", "1.0.post0"),
            ("1.0.post", "1.0.post0"),
            ("1.0post1", "1.0.post1"),
            ("1.0-post", "1.0.post0"),
            ("1.0-post1", "1.0.post1"),
            ("1.0POST", "1.0.post0"),
            ("1.0.POST", "1.0.post0"),
            ("1.0POST1", "1.0.post1"),
            ("1.0r", "1.0.post0"),
            ("1.0rev", "1.0.post0"),
            ("1.0.POST1", "1.0.post1"),
            ("1.0.r1", "1.0.post1"),
            ("1.0.rev1", "1.0.post1"),
            ("1.0-POST", "1.0.post0"),
            ("1.0-POST1", "1.0.post1"),
            ("1.0-5", "1.0.post5"),
            ("1.0-r5", "1.0.post5"),
            ("1.0-rev5", "1.0.post5"),
            # Local version case insensitivity
            ("1.0+AbC", "1.0+abc"),
            # Integer Normalization
            ("1.01", "1.1"),
            ("1.0a05", "1.0a5"),
            ("1.0b07", "1.0b7"),
            ("1.0c056", "1.0rc56"),
            ("1.0rc09", "1.0rc9"),
            ("1.0.post000", "1.0.post0"),
            ("1.1.dev09000", "1.1.dev9000"),
            ("00!1.2", "1.2"),
            ("0100!0.0", "100!0.0"),
            # Various other normalizations
            ("v1.0", "1.0"),
            ("   v1.0\t\n", "1.0"),
        ],
    )
    def test_normalized_versions(self, version: str, normalized: str) -> None:
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
            ("1.0rc1.dev456", "1.0rc1.dev456"),
            ("1.0rc1", "1.0rc1"),
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
            ("7!1.0rc1.dev456", "7!1.0rc1.dev456"),
            ("7!1.0rc1", "7!1.0rc1"),
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
    def test_version_str_repr(self, version: str, expected: str) -> None:
        assert str(Version(version)) == expected
        assert repr(Version(version)) == f"<Version({expected!r})>"

    def test_version_rc_and_c_equals(self) -> None:
        assert Version("1.0rc1") == Version("1.0c1")

    @pytest.mark.parametrize("version", VERSIONS)
    def test_version_hash(self, version: str) -> None:
        assert hash(Version(version)) == hash(Version(version))

    @pytest.mark.parametrize(
        ("version", "public"),
        [
            ("1.0", "1.0"),
            ("1.0.dev0", "1.0.dev0"),
            ("1.0.dev6", "1.0.dev6"),
            ("1.0a1", "1.0a1"),
            ("1.0a1.post5", "1.0a1.post5"),
            ("1.0a1.post5.dev6", "1.0a1.post5.dev6"),
            ("1.0rc4", "1.0rc4"),
            ("1.0.post5", "1.0.post5"),
            ("1!1.0", "1!1.0"),
            ("1!1.0.dev6", "1!1.0.dev6"),
            ("1!1.0a1", "1!1.0a1"),
            ("1!1.0a1.post5", "1!1.0a1.post5"),
            ("1!1.0a1.post5.dev6", "1!1.0a1.post5.dev6"),
            ("1!1.0rc4", "1!1.0rc4"),
            ("1!1.0.post5", "1!1.0.post5"),
            ("1.0+deadbeef", "1.0"),
            ("1.0.dev6+deadbeef", "1.0.dev6"),
            ("1.0a1+deadbeef", "1.0a1"),
            ("1.0a1.post5+deadbeef", "1.0a1.post5"),
            ("1.0a1.post5.dev6+deadbeef", "1.0a1.post5.dev6"),
            ("1.0rc4+deadbeef", "1.0rc4"),
            ("1.0.post5+deadbeef", "1.0.post5"),
            ("1!1.0+deadbeef", "1!1.0"),
            ("1!1.0.dev6+deadbeef", "1!1.0.dev6"),
            ("1!1.0a1+deadbeef", "1!1.0a1"),
            ("1!1.0a1.post5+deadbeef", "1!1.0a1.post5"),
            ("1!1.0a1.post5.dev6+deadbeef", "1!1.0a1.post5.dev6"),
            ("1!1.0rc4+deadbeef", "1!1.0rc4"),
            ("1!1.0.post5+deadbeef", "1!1.0.post5"),
        ],
    )
    def test_version_public(self, version: str, public: str) -> None:
        assert Version(version).public == public

    @pytest.mark.parametrize(
        ("version", "base_version"),
        [
            ("1.0", "1.0"),
            ("1.0.dev0", "1.0"),
            ("1.0.dev6", "1.0"),
            ("1.0a1", "1.0"),
            ("1.0a1.post5", "1.0"),
            ("1.0a1.post5.dev6", "1.0"),
            ("1.0rc4", "1.0"),
            ("1.0.post5", "1.0"),
            ("1!1.0", "1!1.0"),
            ("1!1.0.dev6", "1!1.0"),
            ("1!1.0a1", "1!1.0"),
            ("1!1.0a1.post5", "1!1.0"),
            ("1!1.0a1.post5.dev6", "1!1.0"),
            ("1!1.0rc4", "1!1.0"),
            ("1!1.0.post5", "1!1.0"),
            ("1.0+deadbeef", "1.0"),
            ("1.0.dev6+deadbeef", "1.0"),
            ("1.0a1+deadbeef", "1.0"),
            ("1.0a1.post5+deadbeef", "1.0"),
            ("1.0a1.post5.dev6+deadbeef", "1.0"),
            ("1.0rc4+deadbeef", "1.0"),
            ("1.0.post5+deadbeef", "1.0"),
            ("1!1.0+deadbeef", "1!1.0"),
            ("1!1.0.dev6+deadbeef", "1!1.0"),
            ("1!1.0a1+deadbeef", "1!1.0"),
            ("1!1.0a1.post5+deadbeef", "1!1.0"),
            ("1!1.0a1.post5.dev6+deadbeef", "1!1.0"),
            ("1!1.0rc4+deadbeef", "1!1.0"),
            ("1!1.0.post5+deadbeef", "1!1.0"),
        ],
    )
    def test_version_base_version(self, version: str, base_version: str) -> None:
        assert Version(version).base_version == base_version

    @pytest.mark.parametrize(
        ("version", "epoch"),
        [
            ("1.0", 0),
            ("1.0.dev0", 0),
            ("1.0.dev6", 0),
            ("1.0a1", 0),
            ("1.0a1.post5", 0),
            ("1.0a1.post5.dev6", 0),
            ("1.0rc4", 0),
            ("1.0.post5", 0),
            ("1!1.0", 1),
            ("1!1.0.dev6", 1),
            ("1!1.0a1", 1),
            ("1!1.0a1.post5", 1),
            ("1!1.0a1.post5.dev6", 1),
            ("1!1.0rc4", 1),
            ("1!1.0.post5", 1),
            ("1.0+deadbeef", 0),
            ("1.0.dev6+deadbeef", 0),
            ("1.0a1+deadbeef", 0),
            ("1.0a1.post5+deadbeef", 0),
            ("1.0a1.post5.dev6+deadbeef", 0),
            ("1.0rc4+deadbeef", 0),
            ("1.0.post5+deadbeef", 0),
            ("1!1.0+deadbeef", 1),
            ("1!1.0.dev6+deadbeef", 1),
            ("1!1.0a1+deadbeef", 1),
            ("1!1.0a1.post5+deadbeef", 1),
            ("1!1.0a1.post5.dev6+deadbeef", 1),
            ("1!1.0rc4+deadbeef", 1),
            ("1!1.0.post5+deadbeef", 1),
        ],
    )
    def test_version_epoch(self, version: str, epoch: int) -> None:
        assert Version(version).epoch == epoch

    @pytest.mark.parametrize(
        ("version", "release"),
        [
            ("1.0", (1, 0)),
            ("1.0.dev0", (1, 0)),
            ("1.0.dev6", (1, 0)),
            ("1.0a1", (1, 0)),
            ("1.0a1.post5", (1, 0)),
            ("1.0a1.post5.dev6", (1, 0)),
            ("1.0rc4", (1, 0)),
            ("1.0.post5", (1, 0)),
            ("1!1.0", (1, 0)),
            ("1!1.0.dev6", (1, 0)),
            ("1!1.0a1", (1, 0)),
            ("1!1.0a1.post5", (1, 0)),
            ("1!1.0a1.post5.dev6", (1, 0)),
            ("1!1.0rc4", (1, 0)),
            ("1!1.0.post5", (1, 0)),
            ("1.0+deadbeef", (1, 0)),
            ("1.0.dev6+deadbeef", (1, 0)),
            ("1.0a1+deadbeef", (1, 0)),
            ("1.0a1.post5+deadbeef", (1, 0)),
            ("1.0a1.post5.dev6+deadbeef", (1, 0)),
            ("1.0rc4+deadbeef", (1, 0)),
            ("1.0.post5+deadbeef", (1, 0)),
            ("1!1.0+deadbeef", (1, 0)),
            ("1!1.0.dev6+deadbeef", (1, 0)),
            ("1!1.0a1+deadbeef", (1, 0)),
            ("1!1.0a1.post5+deadbeef", (1, 0)),
            ("1!1.0a1.post5.dev6+deadbeef", (1, 0)),
            ("1!1.0rc4+deadbeef", (1, 0)),
            ("1!1.0.post5+deadbeef", (1, 0)),
        ],
    )
    def test_version_release(self, version: str, release: tuple[int, int]) -> None:
        assert Version(version).release == release

    @pytest.mark.parametrize(
        ("version", "local"),
        [
            ("1.0", None),
            ("1.0.dev0", None),
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
    def test_version_local(self, version: str, local: str | None) -> None:
        assert Version(version).local == local

    @pytest.mark.parametrize(
        ("version", "pre"),
        [
            ("1.0", None),
            ("1.0.dev0", None),
            ("1.0.dev6", None),
            ("1.0a1", ("a", 1)),
            ("1.0a1.post5", ("a", 1)),
            ("1.0a1.post5.dev6", ("a", 1)),
            ("1.0rc4", ("rc", 4)),
            ("1.0.post5", None),
            ("1!1.0", None),
            ("1!1.0.dev6", None),
            ("1!1.0a1", ("a", 1)),
            ("1!1.0a1.post5", ("a", 1)),
            ("1!1.0a1.post5.dev6", ("a", 1)),
            ("1!1.0rc4", ("rc", 4)),
            ("1!1.0.post5", None),
            ("1.0+deadbeef", None),
            ("1.0.dev6+deadbeef", None),
            ("1.0a1+deadbeef", ("a", 1)),
            ("1.0a1.post5+deadbeef", ("a", 1)),
            ("1.0a1.post5.dev6+deadbeef", ("a", 1)),
            ("1.0rc4+deadbeef", ("rc", 4)),
            ("1.0.post5+deadbeef", None),
            ("1!1.0+deadbeef", None),
            ("1!1.0.dev6+deadbeef", None),
            ("1!1.0a1+deadbeef", ("a", 1)),
            ("1!1.0a1.post5+deadbeef", ("a", 1)),
            ("1!1.0a1.post5.dev6+deadbeef", ("a", 1)),
            ("1!1.0rc4+deadbeef", ("rc", 4)),
            ("1!1.0.post5+deadbeef", None),
        ],
    )
    def test_version_pre(self, version: str, pre: None | tuple[str, int]) -> None:
        assert Version(version).pre == pre

    @pytest.mark.parametrize(
        ("version", "expected"),
        [
            ("1.0.dev0", True),
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
    def test_version_is_prerelease(self, version: str, expected: bool) -> None:
        assert Version(version).is_prerelease is expected

    @pytest.mark.parametrize(
        ("version", "dev"),
        [
            ("1.0", None),
            ("1.0.dev0", 0),
            ("1.0.dev6", 6),
            ("1.0a1", None),
            ("1.0a1.post5", None),
            ("1.0a1.post5.dev6", 6),
            ("1.0rc4", None),
            ("1.0.post5", None),
            ("1!1.0", None),
            ("1!1.0.dev6", 6),
            ("1!1.0a1", None),
            ("1!1.0a1.post5", None),
            ("1!1.0a1.post5.dev6", 6),
            ("1!1.0rc4", None),
            ("1!1.0.post5", None),
            ("1.0+deadbeef", None),
            ("1.0.dev6+deadbeef", 6),
            ("1.0a1+deadbeef", None),
            ("1.0a1.post5+deadbeef", None),
            ("1.0a1.post5.dev6+deadbeef", 6),
            ("1.0rc4+deadbeef", None),
            ("1.0.post5+deadbeef", None),
            ("1!1.0+deadbeef", None),
            ("1!1.0.dev6+deadbeef", 6),
            ("1!1.0a1+deadbeef", None),
            ("1!1.0a1.post5+deadbeef", None),
            ("1!1.0a1.post5.dev6+deadbeef", 6),
            ("1!1.0rc4+deadbeef", None),
            ("1!1.0.post5+deadbeef", None),
        ],
    )
    def test_version_dev(self, version: str, dev: int | None) -> None:
        assert Version(version).dev == dev

    @pytest.mark.parametrize(
        ("version", "expected"),
        [
            ("1.0", False),
            ("1.0.dev0", True),
            ("1.0.dev6", True),
            ("1.0a1", False),
            ("1.0a1.post5", False),
            ("1.0a1.post5.dev6", True),
            ("1.0rc4", False),
            ("1.0.post5", False),
            ("1!1.0", False),
            ("1!1.0.dev6", True),
            ("1!1.0a1", False),
            ("1!1.0a1.post5", False),
            ("1!1.0a1.post5.dev6", True),
            ("1!1.0rc4", False),
            ("1!1.0.post5", False),
            ("1.0+deadbeef", False),
            ("1.0.dev6+deadbeef", True),
            ("1.0a1+deadbeef", False),
            ("1.0a1.post5+deadbeef", False),
            ("1.0a1.post5.dev6+deadbeef", True),
            ("1.0rc4+deadbeef", False),
            ("1.0.post5+deadbeef", False),
            ("1!1.0+deadbeef", False),
            ("1!1.0.dev6+deadbeef", True),
            ("1!1.0a1+deadbeef", False),
            ("1!1.0a1.post5+deadbeef", False),
            ("1!1.0a1.post5.dev6+deadbeef", True),
            ("1!1.0rc4+deadbeef", False),
            ("1!1.0.post5+deadbeef", False),
        ],
    )
    def test_version_is_devrelease(self, version: str, expected: bool) -> None:
        assert Version(version).is_devrelease is expected

    @pytest.mark.parametrize(
        ("version", "post"),
        [
            ("1.0", None),
            ("1.0.dev0", None),
            ("1.0.dev6", None),
            ("1.0a1", None),
            ("1.0a1.post5", 5),
            ("1.0a1.post5.dev6", 5),
            ("1.0rc4", None),
            ("1.0.post5", 5),
            ("1!1.0", None),
            ("1!1.0.dev6", None),
            ("1!1.0a1", None),
            ("1!1.0a1.post5", 5),
            ("1!1.0a1.post5.dev6", 5),
            ("1!1.0rc4", None),
            ("1!1.0.post5", 5),
            ("1.0+deadbeef", None),
            ("1.0.dev6+deadbeef", None),
            ("1.0a1+deadbeef", None),
            ("1.0a1.post5+deadbeef", 5),
            ("1.0a1.post5.dev6+deadbeef", 5),
            ("1.0rc4+deadbeef", None),
            ("1.0.post5+deadbeef", 5),
            ("1!1.0+deadbeef", None),
            ("1!1.0.dev6+deadbeef", None),
            ("1!1.0a1+deadbeef", None),
            ("1!1.0a1.post5+deadbeef", 5),
            ("1!1.0a1.post5.dev6+deadbeef", 5),
            ("1!1.0rc4+deadbeef", None),
            ("1!1.0.post5+deadbeef", 5),
        ],
    )
    def test_version_post(self, version: str, post: int | None) -> None:
        assert Version(version).post == post

    @pytest.mark.parametrize(
        ("version", "expected"),
        [
            ("1.0.dev1", False),
            ("1.0", False),
            ("1.0+foo", False),
            ("1.0.post1.dev1", True),
            ("1.0.post1", True),
        ],
    )
    def test_version_is_postrelease(self, version: str, expected: bool) -> None:
        assert Version(version).is_postrelease is expected

    @pytest.mark.parametrize(
        ("left", "right", "op"),
        # Below we'll generate every possible combination of VERSIONS that
        # should be True for the given operator
        itertools.chain.from_iterable(
            # Verify that the less than (<) operator works correctly
            [
                [(x, y, operator.lt) for y in VERSIONS[i + 1 :]]
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
            [[(x, x, operator.eq) for x in VERSIONS]]
            +
            # Verify that the not equal (!=) operator works correctly
            [
                [(x, y, operator.ne) for j, y in enumerate(VERSIONS) if i != j]
                for i, x in enumerate(VERSIONS)
            ]
            +
            # Verify that the greater than equal (>=) operator works correctly
            [
                [(x, y, operator.ge) for y in VERSIONS[: i + 1]]
                for i, x in enumerate(VERSIONS)
            ]
            +
            # Verify that the greater than (>) operator works correctly
            [
                [(x, y, operator.gt) for y in VERSIONS[:i]]
                for i, x in enumerate(VERSIONS)
            ]
        ),
    )
    def test_comparison_true(
        self, left: str, right: str, op: Callable[[Version, Version], bool]
    ) -> None:
        assert op(Version(left), Version(right))

    @pytest.mark.parametrize(
        ("left", "right", "op"),
        # Below we'll generate every possible combination of VERSIONS that
        # should be False for the given operator
        itertools.chain.from_iterable(
            # Verify that the less than (<) operator works correctly
            [
                [(x, y, operator.lt) for y in VERSIONS[: i + 1]]
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
            [[(x, x, operator.ne) for x in VERSIONS]]
            +
            # Verify that the greater than equal (>=) operator works correctly
            [
                [(x, y, operator.ge) for y in VERSIONS[i + 1 :]]
                for i, x in enumerate(VERSIONS)
            ]
            +
            # Verify that the greater than (>) operator works correctly
            [
                [(x, y, operator.gt) for y in VERSIONS[i:]]
                for i, x in enumerate(VERSIONS)
            ]
        ),
    )
    def test_comparison_false(
        self, left: str, right: str, op: Callable[[Version, Version], bool]
    ) -> None:
        assert not op(Version(left), Version(right))

    @pytest.mark.parametrize("op", ["lt", "le", "eq", "ge", "gt", "ne"])
    def test_dunder_op_returns_notimplemented(self, op: str) -> None:
        method = getattr(Version, f"__{op}__")
        assert method(Version("1"), 1) is NotImplemented

    @pytest.mark.parametrize(("op", "expected"), [("eq", False), ("ne", True)])
    def test_compare_other(self, op: str, expected: bool) -> None:
        other = pretend.stub(**{f"__{op}__": lambda _: NotImplemented})

        assert getattr(operator, op)(Version("1"), other) is expected

    def test_major_version(self) -> None:
        assert Version("2.1.0").major == 2

    def test_minor_version(self) -> None:
        assert Version("2.1.0").minor == 1
        assert Version("2").minor == 0

    def test_micro_version(self) -> None:
        assert Version("2.1.3").micro == 3
        assert Version("2.1").micro == 0
        assert Version("2").micro == 0

    # Tests for replace() method
    def test_replace_no_args(self) -> None:
        """replace() with no arguments should return an equivalent version"""
        v = Version("1.2.3a1.post2.dev3+local")
        v_replaced = replace(v)
        assert v == v_replaced
        assert str(v) == str(v_replaced)

    def test_replace_epoch(self) -> None:
        v = Version("1.2.3")
        assert str(replace(v, epoch=2)) == "2!1.2.3"
        assert replace(v, epoch=0).epoch == 0

        v_with_epoch = Version("1!1.2.3")
        assert str(replace(v_with_epoch, epoch=2)) == "2!1.2.3"
        assert str(replace(v_with_epoch, epoch=None)) == "1.2.3"

    def test_replace_release_tuple(self) -> None:
        v = Version("1.2.3")
        assert str(replace(v, release=(2, 0, 0))) == "2.0.0"
        assert str(replace(v, release=(1,))) == "1"
        assert str(replace(v, release=(1, 2, 3, 4, 5))) == "1.2.3.4.5"

    def test_replace_release_none(self) -> None:
        v = Version("1.2.3")
        assert str(replace(v, release=None)) == "0"

    def test_replace_pre_alpha(self) -> None:
        v = Version("1.2.3")
        assert str(replace(v, pre=("a", 1))) == "1.2.3a1"
        assert str(replace(v, pre=("A", 0))) == "1.2.3a0"
        assert str(replace(v, pre=("Alpha", 2))) == "1.2.3a2"

    def test_replace_pre_alpha_none(self) -> None:
        v = Version("1.2.3a1")
        assert str(replace(v, pre=None)) == "1.2.3"

    def test_replace_pre_beta(self) -> None:
        v = Version("1.2.3")
        assert str(replace(v, pre=("b", 1))) == "1.2.3b1"
        assert str(replace(v, pre=("b", 0))) == "1.2.3b0"
        assert str(replace(v, pre=("bEta", 2))) == "1.2.3b2"

    def test_replace_pre_beta_none(self) -> None:
        v = Version("1.2.3b1")
        assert str(replace(v, pre=None)) == "1.2.3"

    def test_replace_pre_rc(self) -> None:
        v = Version("1.2.3")
        assert str(replace(v, pre=("rc", 1))) == "1.2.3rc1"
        assert str(replace(v, pre=("rc", 0))) == "1.2.3rc0"

    def test_replace_pre_rc_none(self) -> None:
        v = Version("1.2.3rc1")
        assert str(replace(v, pre=None)) == "1.2.3"

    def test_replace_post(self) -> None:
        v = Version("1.2.3")
        assert str(replace(v, post=1)) == "1.2.3.post1"
        assert str(replace(v, post=0)) == "1.2.3.post0"

    def test_replace_post_none(self) -> None:
        v = Version("1.2.3.post1")
        assert str(replace(v, post=None)) == "1.2.3"

    def test_replace_dev(self) -> None:
        v = Version("1.2.3")
        assert str(replace(v, dev=1)) == "1.2.3.dev1"
        assert str(replace(v, dev=0)) == "1.2.3.dev0"

    def test_replace_dev_none(self) -> None:
        v = Version("1.2.3.dev1")
        assert str(replace(v, dev=None)) == "1.2.3"

    def test_replace_local_string(self) -> None:
        v = Version("1.2.3")
        assert str(replace(v, local="abc")) == "1.2.3+abc"
        assert str(replace(v, local="abc.123")) == "1.2.3+abc.123"
        assert str(replace(v, local="abc-123")) == "1.2.3+abc.123"

    def test_replace_local_none(self) -> None:
        v = Version("1.2.3+local")
        assert str(replace(v, local=None)) == "1.2.3"

    def test_replace_multiple_components(self) -> None:
        v = Version("1.2.3")
        assert str(replace(v, pre=("a", 1), post=1)) == "1.2.3a1.post1"
        assert str(replace(v, release=(2, 0, 0), pre=("b", 2), dev=1)) == "2.0.0b2.dev1"
        assert str(replace(v, epoch=1, release=(3, 0), local="abc")) == "1!3.0+abc"

    def test_replace_clear_all_optional(self) -> None:
        v = Version("1!1.2.3a1.post2.dev3+local")
        cleared = replace(v, epoch=None, pre=None, post=None, dev=None, local=None)
        assert str(cleared) == "1.2.3"

    def test_replace_preserves_comparison(self) -> None:
        v1 = Version("1.2.3")
        v2 = Version("1.2.4")

        v1_new = replace(v1, release=(1, 2, 4))
        assert v1_new == v2
        assert v1 < v2
        assert v1_new >= v2

    def test_replace_preserves_hash(self) -> None:
        v1 = Version("1.2.3")
        v2 = replace(v1, release=(1, 2, 3))
        assert hash(v1) == hash(v2)

        v3 = replace(v1, release=(2, 0, 0))
        assert hash(v1) != hash(v3)

    def test_replace_returns_same_instance_when_unchanged(self) -> None:
        """replace() returns the exact same object when no components change"""
        v = Version("1.2.3a1.post2.dev3+local")
        assert replace(v) is v
        assert replace(v, epoch=0) is v
        assert replace(v, release=(1, 2, 3)) is v
        assert replace(v, pre=("a", 1)) is v
        assert replace(v, post=2) is v
        assert replace(v, dev=3) is v
        assert replace(v, local="local") is v

    def test_replace_change_pre_type(self) -> None:
        """Can change from one pre-release type to another"""
        v = Version("1.2.3a1")
        assert str(replace(v, pre=("b", 2))) == "1.2.3b2"
        assert str(replace(v, pre=("rc", 1))) == "1.2.3rc1"

        v2 = Version("1.2.3rc5")
        assert str(replace(v2, pre=("a", 0))) == "1.2.3a0"

    def test_replace_invalid_epoch_type(self) -> None:
        v = Version("1.2.3")
        with pytest.raises(InvalidVersion, match="epoch must be non-negative"):
            replace(v, epoch="1")  # type: ignore[arg-type]

    def test_replace_invalid_post_type(self) -> None:
        v = Version("1.2.3")
        with pytest.raises(InvalidVersion, match="post must be non-negative"):
            replace(v, post="1")  # type: ignore[arg-type]

    def test_replace_invalid_dev_type(self) -> None:
        v = Version("1.2.3")
        with pytest.raises(InvalidVersion, match="dev must be non-negative"):
            replace(v, dev="1")  # type: ignore[arg-type]

    def test_replace_invalid_epoch_negative(self) -> None:
        v = Version("1.2.3")
        with pytest.raises(InvalidVersion, match="epoch must be non-negative"):
            replace(v, epoch=-1)

    def test_replace_invalid_release_empty(self) -> None:
        v = Version("1.2.3")
        with pytest.raises(InvalidVersion, match="release must be a non-empty tuple"):
            replace(v, release=())

    def test_replace_invalid_release_tuple_content(self) -> None:
        v = Version("1.2.3")
        with pytest.raises(
            InvalidVersion, match="release must be a non-empty tuple of non-negative"
        ):
            replace(v, release=(1, -2, 3))

    def test_replace_invalid_pre_negative(self) -> None:
        v = Version("1.2.3")
        with pytest.raises(InvalidVersion, match="pre must be a tuple"):
            replace(v, pre=("a", -1))

    def test_replace_invalid_pre_type(self) -> None:
        v = Version("1.2.3")
        with pytest.raises(InvalidVersion, match="pre must be a tuple"):
            replace(v, pre=("x", 1))

    def test_replace_invalid_pre_format(self) -> None:
        v = Version("1.2.3")
        with pytest.raises(InvalidVersion, match="pre must be a tuple"):
            replace(v, pre="a1")  # type: ignore[arg-type]
        with pytest.raises(InvalidVersion, match="pre must be a tuple"):
            replace(v, pre=("a",))  # type: ignore[arg-type]
        with pytest.raises(InvalidVersion, match="pre must be a tuple"):
            replace(v, pre=("a", 1, 2))  # type: ignore[arg-type]

    def test_replace_invalid_post_negative(self) -> None:
        v = Version("1.2.3")
        with pytest.raises(InvalidVersion, match="post must be non-negative"):
            replace(v, post=-1)

    def test_replace_invalid_dev_negative(self) -> None:
        v = Version("1.2.3")
        with pytest.raises(InvalidVersion, match="dev must be non-negative"):
            replace(v, dev=-1)

    def test_replace_invalid_local_string(self) -> None:
        v = Version("1.2.3")
        with pytest.raises(
            InvalidVersion, match="local must be a valid version string"
        ):
            replace(v, local="abc+123")
        with pytest.raises(
            InvalidVersion, match="local must be a valid version string"
        ):
            replace(v, local="+abc")


# Taken from hatchling 1.28
def reset_version_parts(version: Version, **kwargs: typing.Any) -> None:  # noqa: ANN401
    # https://github.com/pypa/packaging/blob/20.9/packaging/version.py#L301-L310
    internal_version = version._version
    parts: dict[str, typing.Any] = {}
    ordered_part_names = ("epoch", "release", "pre", "post", "dev", "local")

    reset = False
    for part_name in ordered_part_names:
        if reset:
            parts[part_name] = kwargs.get(part_name)
        elif part_name in kwargs:
            parts[part_name] = kwargs[part_name]
            reset = True
        else:
            parts[part_name] = getattr(internal_version, part_name)

    version._version = type(internal_version)(**parts)


# These will be deprecated in 26.1, and removed in the future
def test_deprecated__version() -> None:
    v = Version("1.2.3")
    with pytest.warns(DeprecationWarning, match="is private"):
        assert v._version.release == (1, 2, 3)


def test_hatchling_usage__version() -> None:
    v = Version("2.3.4")
    with pytest.warns(DeprecationWarning, match="is private"):
        reset_version_parts(v, post=("post", 1))
    assert v == Version("2.3.4.post1")


@pytest.mark.parametrize(
    ("args", "string"),
    [
        ({"release": (1, 2, 3)}, "1.2.3"),
        ({"release": (1, 2, 3), "epoch": 2}, "2!1.2.3"),
        ({"release": (1, 2, 3), "pre": ("b", 1)}, "1.2.3b1"),
        ({"release": (1, 2, 3), "pre": ("B", 1)}, "1.2.3b1"),
        ({"release": (1, 2, 3), "pre": ("beta", 1)}, "1.2.3b1"),
        ({"release": (1, 2, 3), "post": 2}, "1.2.3post2"),
        ({"release": (1, 2, 3), "dev": 3}, "1.2.3.dev3"),
        ({"release": (1, 2, 3), "local": "abc"}, "1.2.3+abc"),
        (
            {
                "release": (1, 2, 3),
                "epoch": None,
                "pre": None,
                "post": None,
                "dev": None,
                "local": None,
            },
            "1.2.3",
        ),
        (
            {
                "release": (2, 3, 4),
                "epoch": 1,
                "pre": ("a", 5),
                "post": 6,
                "dev": 7,
                "local": "zzz",
            },
            "1!2.3.4a5.post6.dev7+zzz",
        ),
    ],
)
def test_from_parts(args: dict[str, typing.Any], string: str) -> None:
    v = Version.from_parts(**args)
    assert v == Version(string)
