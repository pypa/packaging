from __future__ import annotations

import typing

import pytest

from packaging.filenames import (
    InvalidFilename,
    InvalidWheelFilename,
    SourceFilename,
    WheelFilename,
)
from packaging.tags import Tag
from packaging.version import Version

if typing.TYPE_CHECKING:
    from packaging.utils import BuildTag


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
    fn = SourceFilename(name, version)
    assert str(fn) == expected_filename
    assert fn.original_name == name
    assert fn.original_version == version


@pytest.mark.parametrize(
    ("filename", "error_message"),
    [
        (
            "bad.extension",  # Bad extension
            "Invalid SDist filename (extension must be '.tar.gz')",
        ),
        (
            "extra-hyphens-1.0-9.tar.gz",  # Extra hyphens
            "Invalid SDist filename (name and version parts can not contain hyphens)",
        ),
        (
            "no_hyphen.tar.gz",  # No hyphen
            "Invalid SDist filename (hyphen must separate name and version parts)",
        ),
        (
            ".invalid.name-1.0.tar.gz",  # Name is not valid
            "Invalid SDist filename (invalid project name '.invalid.name')",
        ),
        (
            "invalid.name-1.0.tar.gz",  # Name is not canonical (punctuation)
            "Invalid SDist filename (non-normalized project name 'invalid.name')",
        ),
        (
            "invalid__name-1.0.tar.gz",  # Name is not canonical (punctuation)
            "Invalid SDist filename (non-normalized project name 'invalid__name')",
        ),
        (
            "INVALID_NAME-1.0.tar.gz",  # Name is not canonical (casing)
            "Invalid SDist filename (non-normalized project name 'INVALID_NAME')",
        ),
        (
            "valid_name-badversion.tar.gz",  # Version is not valid
            "Invalid SDist filename (invalid version 'badversion')",
        ),
        (
            "valid_name-01.0.tar.gz",  # Version is not canonical
            "Invalid SDist filename (non-normalized version '01.0')",
        ),
    ],
)
def test_sdist_from_filename_invalid(filename: str, error_message: str) -> None:
    with pytest.raises(InvalidFilename) as e:
        SourceFilename.from_filename(filename, strict=True)

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
            "Invalid wheel filename (invalid project name: 'foo__bar')",
        ),
        (
            "foo#bar-1.0-py3-none-any.whl",  # Invalid name (`#`)
            "Invalid wheel filename (invalid project name: 'foo#bar')",
        ),
        (
            "foobar-1.x-py3-none-any.whl",  # Invalid version (`1.x`)
            "Invalid wheel filename (invalid version: '1.x')",
        ),
        (
            # Build number doesn't start with a digit (`abc`)
            "foo-1.0-abc-py3-none-any.whl",
            "Invalid wheel filename (invalid build number: 'abc')",
        ),
        (
            "foo-1.0-200-py3-none-any-junk.whl",  # Too many dashes (`-junk`)
            "Invalid wheel filename (wrong number of parts)",
        ),
        (
            "fOo-1.0-py3-none-any.whl",  # Non-normalized project name
            "Invalid wheel filename (non-normalized project name 'fOo')",
        ),
        (
            "foo-01.0-py3-none-any.whl",  # Non-normalized version
            "Invalid wheel filename (non-normalized version '01.0')",
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
        # Historically, this is not allowed
        # (
        #    "valid__name",  # Name is not canonical (punctuation)
        #    "1.0",
        #    "valid_name-1.0-py3-none-any.whl",
        # ),
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
            "foo-1.0-py3-none-any.whl",
            "foo",
            Version("1.0"),
            (),
            {Tag("py3", "none", "any")},
        ),
        (
            "some_package-1.0-py3-none-any.whl",
            "some-PACKAGE",
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
            "foo_bar-1.0-42-py2.py3-none-any.whl",
            "foo-bar",
            Version("1.0"),
            (42, ""),
            {Tag("py2", "none", "any"), Tag("py3", "none", "any")},
        ),
    ],
)
def test_compose_wheel_filename(
    filename: str, name: str, version: Version, build: BuildTag | None, tags: set[Tag]
) -> None:
    assert (
        WheelFilename(name, str(version), build or (), tags).to_filename() == filename
    )


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
    assert SourceFilename(name, str(version)).to_filename() == filename
