# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.

from __future__ import annotations

import typing

import pytest

from packaging.filenames import (
    InvalidFilename,
    InvalidWheelFilename,
    SourceDistributionFilename,
    WheelFilename,
)
from packaging.tags import Tag
from packaging.version import Version

if typing.TYPE_CHECKING:
    from packaging.filenames import BuildTag


@pytest.mark.parametrize(
    ("name", "version", "expected_filename"),
    [
        (
            "valid.name",  # Name is not canonical (punctuation)
            "1.0",
            "valid_name-1.0.tar.gz",
        ),
        (
            "valid__name",  # Name is not canonical (punctuation)
            "1.0",
            "valid_name-1.0.tar.gz",
        ),
        (
            "VALID_NAME",  # Name is not canonical (casing)
            "1.0",
            "valid_name-1.0.tar.gz",
        ),
        (
            "valid_name",
            "01.0",  # Version is not canonical
            "valid_name-1.0.tar.gz",
        ),
    ],
)
def test_sdist_not_strict_passes(
    name: str, version: str, expected_filename: str
) -> None:
    fn = SourceDistributionFilename(name, version)
    assert str(fn) == expected_filename
    assert fn.original_name == name
    assert fn.original_version == version


@pytest.mark.parametrize(
    ("filename", "error_message"),
    [
        (
            "bad.extension",  # Bad extension
            "Invalid sdist filename (extension must be '.tar.gz')",
        ),
        (
            "extra-hyphens-1.0-9.tar.gz",  # Extra hyphens
            "Invalid sdist filename (non-normalized project name 'extra-hyphens-1.0')",
        ),
        (
            "no_hyphen.tar.gz",  # No hyphen
            "Invalid sdist filename (hyphen must separate name and version parts)",
        ),
        (
            ".invalid.name-1.0.tar.gz",  # Name is not valid
            "Invalid sdist filename (invalid project name '.invalid.name')",
        ),
        (
            "invalid.name-1.0.tar.gz",  # Name is not canonical (punctuation)
            "Invalid sdist filename (non-normalized project name 'invalid.name')",
        ),
        (
            "invalid__name-1.0.tar.gz",  # Name is not canonical (punctuation)
            "Invalid sdist filename (non-normalized project name 'invalid__name')",
        ),
        (
            "INVALID_NAME-1.0.tar.gz",  # Name is not canonical (casing)
            "Invalid sdist filename (non-normalized project name 'INVALID_NAME')",
        ),
        (
            "valid_name-badversion.tar.gz",  # Version is not valid
            "Invalid sdist filename (invalid version 'badversion')",
        ),
        (
            "valid_name-01.0.tar.gz",  # Version is not canonical
            "Invalid sdist filename (non-normalized version '01.0')",
        ),
    ],
)
def test_sdist_from_filename_invalid(filename: str, error_message: str) -> None:
    with pytest.raises(InvalidFilename) as e:
        SourceDistributionFilename.from_filename(filename, strict=True)

    assert str(e.value) == f"{error_message}: {filename!r}"


# Wheels
@pytest.mark.parametrize(
    ("filename", "name", "version", "build_tag", "tags"),
    [
        (
            "foo-1.0-py3-none-any.whl",
            "foo",
            Version("1.0"),
            (),
            {Tag("py3", "none", "any")},
        ),
        (
            "some_package-1.0-py3-none-any.whl",
            "some-package",
            Version("1.0"),
            (),
            {Tag("py3", "none", "any")},
        ),
        (
            "foo-1.0-1000-py3-none-any.whl",
            "foo",
            Version("1.0"),
            (1000, ""),
            {Tag("py3", "none", "any")},
        ),
        (
            "foo-1.0-1000abc-py3-none-any.whl",
            "foo",
            Version("1.0"),
            (1000, "abc"),
            {Tag("py3", "none", "any")},
        ),
        (
            "foo-1.0-py2.py3-none-any.whl",  # Sorted multiple interpreter tags
            "foo",
            Version("1.0"),
            (),
            {Tag("py2", "none", "any"), Tag("py3", "none", "any")},
        ),
        (  # Sorted multiple platform tags
            "numpy-1.23.3-cp310-cp310-manylinux2014_x86_64.manylinux_2_17_x86_64.whl",
            "numpy",
            Version("1.23.3"),
            (),
            {
                Tag("cp310", "cp310", "manylinux2014_x86_64"),
                Tag("cp310", "cp310", "manylinux_2_17_x86_64"),
            },
        ),
    ],
)
def test_wheel_from_filename(
    filename: str, name: str, version: Version, build_tag: BuildTag, tags: set[Tag]
) -> None:
    fn = WheelFilename.from_filename(filename, strict=True)
    assert fn.name == name
    assert fn.version == version
    assert fn.build_tag == build_tag
    assert fn.tags == tags
    assert fn.variant is None
    assert fn.to_filename() == filename


@pytest.mark.parametrize(
    ("filename", "build_tag", "tags", "variant"),
    [
        (
            "numpy-2.3.2-cp313-cp313t-musllinux_1_2_x86_64-x86_64_v3.whl",
            (),
            {Tag("cp313", "cp313t", "musllinux_1_2_x86_64")},
            "x86_64_v3",
        ),
        (
            "numpy-2.3.2-1-cp313-cp313t-musllinux_1_2_x86_64-x86_64_v3.whl",
            (1, ""),
            {Tag("cp313", "cp313t", "musllinux_1_2_x86_64")},
            "x86_64_v3",
        ),
        (
            "numpy-2.3.2-py2.py3-none-any-null.whl",
            (),
            {Tag("py2", "none", "any"), Tag("py3", "none", "any")},
            "null",
        ),
        (
            "numpy-2.3.2-12ab-py3-none-any-0.a_b.whl",
            (12, "ab"),
            {Tag("py3", "none", "any")},
            "0.a_b",
        ),
    ],
)
def test_wheel_from_filename_variant(
    filename: str, build_tag: BuildTag, tags: set[Tag], variant: str
) -> None:
    fn = WheelFilename.from_filename(filename, strict=True)
    assert fn.name == "numpy"
    assert fn.version == Version("2.3.2")
    assert fn.build_tag == build_tag
    assert fn.tags == tags
    assert fn.variant == variant
    assert fn.to_filename() == filename


@pytest.mark.parametrize(
    ("filename", "error_message"),
    [
        (
            "foo-1.0.whl",  # Missing tags
            "Invalid wheel filename (wrong number of parts)",
        ),
        (
            "foo-1.0-py3-none-any.wheel",  # Incorrect file extension (`.wheel`)
            "Invalid wheel filename (extension must be '.whl')",
        ),
        (
            "foo__bar-1.0-py3-none-any.whl",  # Invalid name (`__`)
            "Invalid wheel filename (invalid project name 'foo__bar')",
        ),
        (
            "foo#bar-1.0-py3-none-any.whl",  # Invalid name (`#`)
            "Invalid wheel filename (invalid project name 'foo#bar')",
        ),
        (
            "foobar-1.x-py3-none-any.whl",  # Invalid version (`1.x`)
            "Invalid wheel filename (invalid version '1.x')",
        ),
        (
            # Too many dashes (`-junk-more`)
            "foo-1.0-200-py3-none-any-junk-more.whl",
            "Invalid wheel filename (wrong number of parts)",
        ),
        (
            "foo-1.0-abc-py3-none-any-x86.whl",  # Build number without a digit
            "Invalid wheel filename (invalid build number 'abc')",
        ),
        (
            "foo-1.0-py3-none-any-X86.whl",  # Upper case variant label
            "Invalid wheel filename (invalid variant label 'X86')",
        ),
        (
            "foo-1.0-1-py3-none-any-abcdefghijklmnopq.whl",  # Label too long
            "Invalid wheel filename (invalid variant label 'abcdefghijklmnopq')",
        ),
        (
            "foo-1.0-1-py3-none-any-a+b.whl",  # Invalid character in label
            "Invalid wheel filename (invalid variant label 'a+b')",
        ),
        (
            "fOo-1.0-py3-none-any.whl",  # Non-normalized project name
            "Invalid wheel filename (non-normalized project name 'fOo')",
        ),
        (
            "_foo-1.0-py3-none-any.whl",  # Leading underscore
            "Invalid wheel filename (invalid project name '_foo')",
        ),
        (
            "\u00e9-1.0-py3-none-any.whl",  # Non-ASCII name
            "Invalid wheel filename (invalid project name '\u00e9')",
        ),
        (
            "foo-01.0-py3-none-any.whl",  # Non-normalized version
            "Invalid wheel filename (non-normalized version '01.0')",
        ),
        (
            "foo-1.0-01-py3-none-any.whl",  # Non-normalized build tag
            "Invalid wheel filename (non-normalized build tag '01')",
        ),
        (  # Unsorted interpreter tags (py3 before py2)
            "foo-1.0-py3.py2-none-any.whl",
            "Invalid wheel filename (compressed tag set components must be in "
            "sorted order per PEP 425)",
        ),
        (
            # Unsorted platform tags (manylinux_ before manylinux2014)
            "numpy-1.23.3-cp310-cp310-manylinux_2_17_x86_64.manylinux2014_x86_64.whl",
            "Invalid wheel filename (compressed tag set components must be in "
            "sorted order per PEP 425)",
        ),
        (  # Duplicate interpreter tags
            "foo-1.0-py3.py3-none-any.whl",
            "Invalid wheel filename (non-normalized tags 'py3.py3-none-any')",
        ),
    ],
)
def test_wheel_from_filename_invalid(filename: str, error_message: str) -> None:
    with pytest.raises(InvalidWheelFilename) as e:
        WheelFilename.from_filename(filename, strict=True)

    assert str(e.value) == f"{error_message}: {filename!r}"


@pytest.mark.parametrize(
    ("name", "version", "expected_filename"),
    [
        (
            "valid.name",  # Name is not canonical (punctuation)
            "1.0",
            "valid_name-1.0-py3-none-any.whl",
        ),
        (
            "valid__name",  # Name is not canonical (punctuation)
            "1.0",
            "valid_name-1.0-py3-none-any.whl",
        ),
        (
            "VALID_NAME",  # Name is not canonical (casing)
            "1.0",
            "valid_name-1.0-py3-none-any.whl",
        ),
        (
            "valid_name",
            "01.0",  # Version is not canonical
            "valid_name-1.0-py3-none-any.whl",
        ),
    ],
)
def test_wheel_not_strict_passes(
    name: str, version: str, expected_filename: str
) -> None:
    fn = WheelFilename(name, version, (), {Tag("py3", "none", "any")})
    assert str(fn) == expected_filename
    assert fn.original_name == name
    assert fn.original_version == version


@pytest.mark.parametrize(
    ("filename", "name", "version", "build", "tags"),
    [
        (
            "some_package-1.0-py3-none-any.whl",
            "some-PACKAGE",
            "1.0",
            (),
            {Tag("py3", "none", "any")},
        ),
        (
            "foo_bar-1.0-42-py2.py3-none-any.whl",
            "foo-bar",
            "01.0",
            (42, ""),
            {Tag("py2", "none", "any"), Tag("py3", "none", "any")},
        ),
    ],
)
def test_compose_wheel_filename(
    filename: str, name: str, version: str, build: BuildTag, tags: set[Tag]
) -> None:
    assert WheelFilename(name, version, build, tags).to_filename() == filename


def test_parse_and_create_filename() -> None:
    filename = "numpy-1.23.3-cp310-cp310-manylinux_2_17_x86_64.manylinux2014_x86_64.whl"
    sorted_f = "numpy-1.23.3-cp310-cp310-manylinux2014_x86_64.manylinux_2_17_x86_64.whl"

    wf = WheelFilename.from_filename(filename, strict=False)
    composed = wf.to_filename()
    assert sorted_f == composed


@pytest.mark.parametrize(
    ("filename", "name", "version"),
    [
        ("foo-1.0.tar.gz", "foo", Version("1.0")),
        ("foo_bar-1.0.tar.gz", "foo-bar", Version("1.0")),
    ],
)
def test_compose_sdist_filename(filename: str, name: str, version: Version) -> None:
    assert SourceDistributionFilename(name, str(version)).to_filename() == filename


def test_sdist_from_filename_strict_valid() -> None:
    fn = SourceDistributionFilename.from_filename("foo_bar-1.0.tar.gz", strict=True)
    assert fn.name == "foo-bar"
    assert fn.version == Version("1.0")


def test_wheel_version_property_invalid() -> None:
    wf = WheelFilename("foo", "not-a-version", (), {Tag("py3", "none", "any")})
    with pytest.raises(InvalidWheelFilename, match="invalid version"):
        _ = wf.version


def test_wheel_repr() -> None:
    tags = frozenset({Tag("py3", "none", "any")})
    wf = WheelFilename("foo", "1.0", (1, "abc"), tags)
    assert repr(wf) == (
        f"WheelFilename(name='foo', version='1.0', build_tag=(1, 'abc'), "
        f"tags={tags!r}, variant=None)"
    )


def test_sdist_version_property_invalid() -> None:
    fn = SourceDistributionFilename("foo", "not-a-version")
    with pytest.raises(InvalidFilename, match="invalid version"):
        _ = fn.version


def test_sdist_repr() -> None:
    fn = SourceDistributionFilename("foo", "1.0")
    assert repr(fn) == "SourceDistributionFilename(name='foo', version='1.0')"


def test_sdist_from_filename_invalid_extension_not_strict() -> None:
    with pytest.raises(InvalidFilename) as e:
        SourceDistributionFilename.from_filename("foo-1.0.tgz", strict=False)

    assert str(e.value) == (
        "Invalid sdist filename (extension must be '.tar.gz' or '.zip'): 'foo-1.0.tgz'"
    )


def test_wheel_from_filename_six_parts_non_digit_is_variant() -> None:
    # PEP 825: a third part that does not start with a digit is a Python tag.
    fn = WheelFilename.from_filename("foo-1.0-abc-py3-none-any.whl", strict=True)
    assert fn.build_tag == ()
    assert fn.tags == {Tag("abc", "py3", "none")}
    assert fn.variant == "any"


def test_wheel_to_filename_no_tags() -> None:
    wf = WheelFilename("foo", "1.0")
    with pytest.raises(InvalidWheelFilename, match="at least one tag"):
        wf.to_filename()


def test_wheel_to_filename_tags_not_compressible() -> None:
    tags = {Tag("py3", "none", "any"), Tag("cp314", "cp314", "win_amd64")}
    wf = WheelFilename("foo", "1.0", (), tags)
    with pytest.raises(InvalidWheelFilename, match="cannot be compressed"):
        wf.to_filename()


def test_wheel_eq_hash() -> None:
    tags = {Tag("py3", "none", "any")}
    wf = WheelFilename("foo", "1.0", (1, ""), tags)
    assert wf == WheelFilename("foo", "1.0", (1, ""), tags)
    assert hash(wf) == hash(WheelFilename("foo", "1.0", (1, ""), tags))
    assert wf != WheelFilename("Foo", "1.0", (1, ""), tags)
    assert wf != WheelFilename("foo", "1.0", (), tags)
    assert wf != WheelFilename("foo", "1.0", (1, ""), tags, "x86_64_v3")
    assert wf != "foo-1.0-1-py3-none-any.whl"
    assert len({wf, WheelFilename.from_filename(str(wf), strict=True)}) == 1


def test_sdist_eq_hash() -> None:
    fn = SourceDistributionFilename("foo", "1.0")
    assert fn == SourceDistributionFilename("foo", "1.0")
    assert hash(fn) == hash(SourceDistributionFilename("foo", "1.0"))
    assert fn != SourceDistributionFilename("foo", "1.0.0")
    assert fn != "foo-1.0.tar.gz"
    assert fn != WheelFilename("foo", "1.0")
