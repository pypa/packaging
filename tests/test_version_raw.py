# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.

import copy
import pickle

import pytest

from packaging.version import Version, _TrimmedRelease, _Version


@pytest.mark.parametrize(
    ("raw", "normalized"),
    [
        ("2026.01.01", "2026.1.1"),
        (" \tV2026.01.01RC01 \n", "2026.1.1rc1"),
    ],
)
def test_raw_version(raw: str, normalized: str) -> None:
    version = Version(raw)
    other = Version(normalized)
    assert version.raw_version == raw
    assert str(version) == normalized
    assert repr(version) == f"<Version({normalized!r})>"
    assert version == other
    assert hash(version) == hash(other)
    assert len({version, other}) == 1
    assert {version: "value"}[other] == "value"
    assert Version("2025") < version < Version("2027")
    with pytest.raises(AttributeError):
        version.raw_version = "other"
    with pytest.raises(AttributeError):
        delattr(version, "raw_version")


def test_raw_version_derived_paths() -> None:
    version = Version("2026.01.01")
    assert Version.from_parts(release=(2026, 1, 1)).raw_version is None
    assert _TrimmedRelease(version).raw_version is None
    assert _TrimmedRelease("2026.01.01").raw_version == "2026.01.01"
    changed = version.__replace__(dev=1)
    assert changed is not version
    assert changed.raw_version is None
    assert str(changed) == "2026.1.1.dev1"
    assert version.__replace__() is version
    assert version.__replace__(release=(2026, 1, 1)) is version
    assert version.raw_version == "2026.01.01"
    padded = Version("01.00")
    replaced = padded.__replace__(release=(1, 0, 0))
    assert replaced is not padded
    assert replaced == padded
    assert replaced.raw_version is None


def test_raw_version_pickle_and_copy() -> None:
    version = Version("01!02.03.04A05.post06.dev07+ZZZ")
    assert version.__getstate__() == (
        1,
        (2, 3, 4),
        ("a", 5),
        ("post", 6),
        ("dev", 7),
        ("zzz",),
    )
    # Supplied packaging 26.2+ protocol-2 baseline, without raw provenance.
    baseline = (
        b"\x80\x02cpackaging.version\nVersion\nq\x00)\x81q\x01(K\x01K\x02K\x03"
        b"K\x04\x87q\x02X\x01\x00\x00\x00aq\x03K\x05\x86q\x04X\x04\x00\x00"
        b"\x00postq\x05K\x06\x86q\x06X\x03\x00\x00\x00devq\x07K\x07\x86q\x08"
        b"X\x03\x00\x00\x00zzzq\t\x85q\ntq\x0bb."
    )
    assert pickle.dumps(version, protocol=2) == baseline
    for restored in (
        pickle.loads(baseline),
        pickle.loads(pickle.dumps(version)),
        copy.copy(version),
        copy.deepcopy(version),
    ):
        assert restored.raw_version is None
        assert restored == version
        assert hash(restored) == hash(version)
        assert str(restored) == str(version)
        assert repr(restored) == repr(version)


@pytest.mark.parametrize(
    "state",
    [
        (0, (2026, 1, 1), None, None, None, None),
        (None, {"_epoch": 0, "_release": (2026, 1, 1)}),
        {"_version": _Version(0, (2026, 1, 1), None, None, None, None)},
    ],
)
def test_raw_version_restoration(state: object) -> None:
    for version in (Version.__new__(Version), Version("2025.01")):
        version.__setstate__(state)
        assert version.raw_version is None
        assert version == Version("2026.1.1")
        assert str(version) == "2026.1.1"


@pytest.mark.parametrize("release", [(2026, 1, 1), (2027, 1, 1)])
def test_raw_version_private_setter(release: tuple[int, ...]) -> None:
    version = Version("2026.01.01")
    hash(version)
    with pytest.warns(DeprecationWarning, match="Version[.]_version is private"):
        version._version = _Version(0, release, None, None, None, None)
    assert version.raw_version is None
    expected = Version.from_parts(release=release)
    assert version == expected
    assert hash(version) == hash(expected)
