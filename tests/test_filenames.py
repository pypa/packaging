# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.

from __future__ import annotations

import copy
import pickle
import re
import subprocess
import sys
import typing

import pytest

from packaging.errors import ExceptionGroup
from packaging.filenames import (
    InvalidFilename,
    InvalidProjectName,
    InvalidSdistFilename,
    InvalidWheelFilename,
    NonNormalizedBuildTag,
    NonNormalizedName,
    NonNormalizedTags,
    NonNormalizedVersion,
    NormalizedSdistFilename,
    NormalizedWheelFilename,
    SourceDistributionFilename,
    UnsortedWheelTags,
    WheelFilename,
    ZipSdistFilename,
)
from packaging.tags import Tag
from packaging.utils import canonicalize_name
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
        ("foo", "1.0", "foo-1.0.tar.gz"),
        ("foo-bar", "1.0", "foo_bar-1.0.tar.gz"),
    ],
)
def test_sdist_init(name: str, version: str, expected_filename: str) -> None:
    raw = SourceDistributionFilename(name, version)
    assert raw.to_filename() == str(raw) == f"{name}-{version}.tar.gz"
    assert (raw.name, raw.version, raw.extension) == (name, version, ".tar.gz")
    assert raw == SourceDistributionFilename.from_filename(str(raw))
    fn = raw.normalize()
    assert fn.to_filename() == expected_filename
    assert str(fn) == expected_filename
    assert fn.name == canonicalize_name(name)
    assert fn.version == Version(version)
    assert fn == NormalizedSdistFilename(name, Version(version))
    expected = SourceDistributionFilename.from_filename(expected_filename)
    assert expected.normalize(strict=True) == fn


@pytest.mark.parametrize(
    ("filename", "error_message", "error_type"),
    [
        (
            "bad.extension",  # Bad extension
            "Invalid sdist filename (extension must be '.tar.gz' or '.zip')",
            InvalidSdistFilename,
        ),
        (
            "foo-1.0.zip",  # Legacy extension
            "Invalid sdist filename (extension must be '.tar.gz')",
            ZipSdistFilename,
        ),
        (
            "extra-hyphens-1.0-9.tar.gz",  # Extra hyphens
            "Invalid sdist filename (non-normalized project name 'extra-hyphens-1.0', "
            "should be 'extra_hyphens_1_0')",
            NonNormalizedName,
        ),
        (
            "no_hyphen.tar.gz",  # No hyphen
            "Invalid sdist filename (hyphen must separate name and version parts)",
            InvalidSdistFilename,
        ),
        (
            ".invalid.name-1.0.tar.gz",  # Name is not valid
            "Invalid sdist filename (invalid project name '.invalid.name')",
            InvalidProjectName,
        ),
        (
            "invalid.name-1.0.tar.gz",  # Name is not canonical (punctuation)
            "Invalid sdist filename (non-normalized project name 'invalid.name', "
            "should be 'invalid_name')",
            NonNormalizedName,
        ),
        (
            "invalid__name-1.0.tar.gz",  # Name is not canonical (punctuation)
            "Invalid sdist filename (non-normalized project name 'invalid__name', "
            "should be 'invalid_name')",
            NonNormalizedName,
        ),
        (
            "INVALID_NAME-1.0.tar.gz",  # Name is not canonical (casing)
            "Invalid sdist filename (non-normalized project name 'INVALID_NAME', "
            "should be 'invalid_name')",
            NonNormalizedName,
        ),
        (
            "valid_name-badversion.tar.gz",  # Version is not valid
            "Invalid sdist filename (invalid version 'badversion')",
            InvalidSdistFilename,
        ),
        (
            "valid_name-01.0.tar.gz",  # Version is not canonical
            "Invalid sdist filename (non-normalized version '01.0', should be '1.0')",
            NonNormalizedVersion,
        ),
    ],
)
def test_strict_sdist_filename_invalid(
    filename: str, error_message: str, error_type: type[InvalidFilename]
) -> None:
    with pytest.raises((InvalidFilename, ExceptionGroup)) as e:
        SourceDistributionFilename.from_filename(filename).normalize(strict=True)

    if isinstance(e.value, ExceptionGroup):
        message = f"Non-normalized sdist filename: {filename!r}"
        if error_type is not InvalidProjectName:
            raw = SourceDistributionFilename.from_filename(filename)
            expected = raw.normalize().to_filename()
            message += f", should be {expected!r}"
        assert e.value.message == message
        (error,) = e.value.exceptions
    else:
        error = e.value
    assert type(error) is error_type
    assert str(error) == f"{error_message}: {filename!r}"


@pytest.mark.parametrize(
    ("filename", "error_types"),
    [
        ("Foo-01.0.tar.gz", [NonNormalizedName, NonNormalizedVersion]),
        ("Foo-01.0.zip", [ZipSdistFilename, NonNormalizedName, NonNormalizedVersion]),
    ],
)
def test_strict_sdist_filename_multiple_errors(
    filename: str, error_types: list[type[InvalidFilename]]
) -> None:
    with pytest.raises(ExceptionGroup) as e:
        SourceDistributionFilename.from_filename(filename).normalize(strict=True)

    assert [type(error) for error in e.value.exceptions] == error_types


@pytest.mark.parametrize(
    "filename",
    ["foo-0.tar.gz", "foo_bar-10.20.0.tar.gz", "foo-1!2.0rc1.post2.dev3.tar.gz"],
)
def test_strict_sdist_filename_valid(filename: str) -> None:
    SourceDistributionFilename.from_filename(filename).normalize(strict=True)


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
    raw = WheelFilename.from_filename(filename)
    assert raw.to_filename() == str(raw) == filename
    assert raw.variant is None
    fn = raw.normalize(strict=True)
    assert fn.name == name
    assert fn.version == version
    assert fn.build_tag == build_tag
    assert fn.build_str == (raw.build_tag or "")
    assert fn.tags == tags
    assert fn.compressed_tags == raw.tags
    assert fn.variant is None
    assert fn.to_filename() == str(fn) == filename
    assert fn == NormalizedWheelFilename(name, version, tags, build_tag=build_tag)


@pytest.mark.parametrize(
    ("filename", "name", "build_tag", "tags", "variant"),
    [
        (
            "numpy-2.3.2-cp313-cp313t-musllinux_1_2_x86_64-x86_64_v3.whl",
            "numpy",
            (),
            {Tag("cp313", "cp313t", "musllinux_1_2_x86_64")},
            "x86_64_v3",
        ),
        (
            "numpy-2.3.2-1-cp313-cp313t-musllinux_1_2_x86_64-x86_64_v3.whl",
            "numpy",
            (1, ""),
            {Tag("cp313", "cp313t", "musllinux_1_2_x86_64")},
            "x86_64_v3",
        ),
        (
            "numpy-2.3.2-py2.py3-none-any-null.whl",
            "numpy",
            (),
            {Tag("py2", "none", "any"), Tag("py3", "none", "any")},
            "null",
        ),
        (
            "numpy-2.3.2-12ab-py3-none-any-0.a_b.whl",
            "numpy",
            (12, "ab"),
            {Tag("py3", "none", "any")},
            "0.a_b",
        ),
        (  # A third part that does not start with a digit is a Python tag.
            "foo-1.0-abc-py3-none-any.whl",
            "foo",
            (),
            {Tag("abc", "py3", "none")},
            "any",
        ),
    ],
)
def test_wheel_from_filename_variant(
    filename: str, name: str, build_tag: BuildTag, tags: set[Tag], variant: str
) -> None:
    raw = WheelFilename.from_filename(filename)
    assert raw.variant == variant
    fn = raw.normalize(strict=True)
    assert fn.name == name
    assert fn.build_tag == build_tag
    assert fn.tags == tags
    assert fn.variant == variant
    assert fn.to_filename() == filename
    assert fn == NormalizedWheelFilename(
        name, fn.version, tags, build_tag=build_tag, variant=variant
    )


@pytest.mark.parametrize(
    "filename",
    [
        "foo-0-py3-none-any.whl",
        "foo_bar-10.20.0-1-py2.py3-none-any.whl",
        "foo-1!2.0rc1.post2.dev3+local.1-cp312-cp312-win_amd64.whl",
        "foo-1.0-py3-none-any-abc.whl",
        # These fail the fast checks during parsing, but are normalized.
        "foo-1.0-0-py3-none-any.whl",
        "foo-1.0-1abc-py3-none-any.whl",
        "foo-1.0-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.whl",
    ],
)
def test_strict_wheel_filename_valid(filename: str) -> None:
    WheelFilename.from_filename(filename).normalize(strict=True)


@pytest.mark.parametrize(
    ("filename", "error_message", "error_type"),
    [
        (
            "foo-1.0.whl",  # Missing tags
            "Invalid wheel filename (wrong number of parts)",
            InvalidWheelFilename,
        ),
        (
            "foo-1.0-py3-none-any.wheel",  # Incorrect file extension (`.wheel`)
            "Invalid wheel filename (extension must be '.whl')",
            InvalidWheelFilename,
        ),
        (
            "foo__bar-1.0-py3-none-any.whl",  # Invalid name (`__`)
            "Invalid wheel filename (invalid project name 'foo__bar')",
            InvalidWheelFilename,
        ),
        (
            "foo#bar-1.0-py3-none-any.whl",  # Invalid name (`#`)
            "Invalid wheel filename (invalid project name 'foo#bar')",
            InvalidWheelFilename,
        ),
        (
            "foobar-1.x-py3-none-any.whl",  # Invalid version (`1.x`)
            "Invalid wheel filename (invalid version '1.x')",
            InvalidWheelFilename,
        ),
        (
            # Too many dashes (`-junk-more`)
            "foo-1.0-200-py3-none-any-junk-more.whl",
            "Invalid wheel filename (wrong number of parts)",
            InvalidWheelFilename,
        ),
        (
            "foo-1.0-abc-py3-none-any-x86.whl",  # Build number without a digit
            "Invalid wheel filename (invalid build number 'abc')",
            InvalidWheelFilename,
        ),
        (
            "foo-1.0-py3-none-any-X86.whl",  # Upper case variant label
            "Invalid wheel filename (invalid variant label 'X86')",
            InvalidWheelFilename,
        ),
        (
            "foo-1.0-1-py3-none-any-abcdefghijklmnopq.whl",  # Label too long
            "Invalid wheel filename (invalid variant label 'abcdefghijklmnopq')",
            InvalidWheelFilename,
        ),
        (
            "foo-1.0-1-py3-none-any-a+b.whl",  # Invalid character in label
            "Invalid wheel filename (invalid variant label 'a+b')",
            InvalidWheelFilename,
        ),
        (
            "fOo-1.0-py3-none-any.whl",  # Non-normalized project name
            "Invalid wheel filename (non-normalized project name 'fOo', "
            "should be 'foo')",
            NonNormalizedName,
        ),
        (
            "_foo-1.0-py3-none-any.whl",  # Leading underscore
            "Invalid wheel filename (invalid project name '_foo')",
            InvalidProjectName,
        ),
        (
            "\u00e9-1.0-py3-none-any.whl",  # Non-ASCII name
            "Invalid wheel filename (invalid project name '\u00e9')",
            InvalidProjectName,
        ),
        (
            "foo-1.0-1 abc-py3-none-any.whl",  # Build tag suffix with a space
            "Invalid wheel filename (invalid build tag '1 abc')",
            InvalidWheelFilename,
        ),
        (
            "foo-1.0-1\nx-py3-none-any.whl",  # Build tag suffix with a newline
            "Invalid wheel filename (invalid build tag '1\\nx')",
            InvalidWheelFilename,
        ),
        (
            "foo-1.0-1\u00e9-py3-none-any.whl",  # Non-ASCII build tag suffix
            "Invalid wheel filename (invalid build tag '1\u00e9')",
            InvalidWheelFilename,
        ),
        (
            "foo-01.0-py3-none-any.whl",  # Non-normalized version
            "Invalid wheel filename (non-normalized version '01.0', should be '1.0')",
            NonNormalizedVersion,
        ),
        (
            "foo-1.0-01-py3-none-any.whl",  # Non-normalized build tag
            "Invalid wheel filename (non-normalized build tag '01', should be '1')",
            NonNormalizedBuildTag,
        ),
        (  # Unsorted interpreter tags (py3 before py2)
            "foo-1.0-py3.py2-none-any.whl",
            "Invalid wheel filename (compressed tag set components must be in "
            "sorted order per PEP 425, should be 'py2.py3-none-any')",
            UnsortedWheelTags,
        ),
        (
            # Unsorted platform tags (manylinux_ before manylinux2014)
            "numpy-1.23.3-cp310-cp310-manylinux_2_17_x86_64.manylinux2014_x86_64.whl",
            "Invalid wheel filename (compressed tag set components must be in "
            "sorted order per PEP 425, should be "
            "'cp310-cp310-manylinux2014_x86_64.manylinux_2_17_x86_64')",
            UnsortedWheelTags,
        ),
        (  # Duplicate interpreter tags
            "foo-1.0-py3.py3-none-any.whl",
            "Invalid wheel filename (non-normalized tags 'py3.py3-none-any', "
            "should be 'py3-none-any')",
            NonNormalizedTags,
        ),
        (  # Uppercase tags
            "foo-1.0-PY3-none-any.whl",
            "Invalid wheel filename (non-normalized tags 'PY3-none-any', "
            "should be 'py3-none-any')",
            NonNormalizedTags,
        ),
        (  # Non-normalized post-release
            "foo-1.0post1-py3-none-any.whl",
            "Invalid wheel filename (non-normalized version '1.0post1', "
            "should be '1.0.post1')",
            NonNormalizedVersion,
        ),
    ],
)
def test_strict_wheel_filename_invalid(
    filename: str, error_message: str, error_type: type[InvalidFilename]
) -> None:
    with pytest.raises((InvalidFilename, ExceptionGroup)) as e:
        WheelFilename.from_filename(filename).normalize(strict=True)

    if isinstance(e.value, ExceptionGroup):
        message = f"Non-normalized wheel filename: {filename!r}"
        if error_type is not InvalidProjectName:
            raw = WheelFilename.from_filename(filename)
            expected = raw.normalize().to_filename()
            message += f", should be {expected!r}"
        assert e.value.message == message
        (error,) = e.value.exceptions
    else:
        error = e.value
    assert type(error) is error_type
    assert str(error) == f"{error_message}: {filename!r}"


@pytest.mark.parametrize(
    ("filename", "error_types"),
    [
        (
            "Foo-01.0-01-py3.py2-none-any.whl",
            [
                NonNormalizedName,
                NonNormalizedVersion,
                NonNormalizedBuildTag,
                UnsortedWheelTags,
            ],
        ),
        ("foo-01.0-py3.py3-none-any.whl", [NonNormalizedVersion, NonNormalizedTags]),
        ("_foo-01.0-py3-none-any.whl", [InvalidProjectName, NonNormalizedVersion]),
    ],
)
def test_strict_wheel_filename_multiple_errors(
    filename: str, error_types: list[type[InvalidFilename]]
) -> None:
    with pytest.raises(ExceptionGroup) as e:
        WheelFilename.from_filename(filename).normalize(strict=True)

    assert [type(error) for error in e.value.exceptions] == error_types


@pytest.mark.parametrize(
    ("name", "version", "build_tag", "tags", "expected_filename"),
    [
        ("valid.name", "1.0", (), None, "valid_name-1.0-py3-none-any.whl"),
        ("valid__name", "1.0", (), None, "valid_name-1.0-py3-none-any.whl"),
        ("VALID_NAME", "1.0", (), None, "valid_name-1.0-py3-none-any.whl"),
        ("valid_name", "01.0", (), None, "valid_name-1.0-py3-none-any.whl"),
        ("some-PACKAGE", "1.0", (), None, "some_package-1.0-py3-none-any.whl"),
        (
            "foo-bar",
            "01.0",
            (42, ""),
            {Tag("py2", "none", "any"), Tag("py3", "none", "any")},
            "foo_bar-1.0-42-py2.py3-none-any.whl",
        ),
    ],
)
def test_normalized_wheel_init(
    name: str,
    version: str,
    build_tag: BuildTag,
    tags: set[Tag] | None,
    expected_filename: str,
) -> None:
    fn = NormalizedWheelFilename(
        name, Version(version), tags or {Tag("py3", "none", "any")}, build_tag=build_tag
    )
    assert fn.to_filename() == expected_filename
    assert str(fn) == expected_filename
    assert fn.name == canonicalize_name(name)
    assert fn.version == Version(version)
    expected = WheelFilename.from_filename(expected_filename)
    assert expected.normalize(strict=True) == fn


@pytest.mark.parametrize(
    ("kwargs", "error_message"),
    [
        ({"name": ""}, "(invalid project name '')"),
        ({"name": "foo bar!"}, "(invalid project name 'foo bar!')"),
        ({"name": "_foo"}, "(invalid project name '_foo')"),
        ({"version": "1.0"}, "does not parse to the given parts"),
        ({"build_tag": (-1, "")}, "invalid build number ''"),
        ({"build_tag": (1, "2")}, "does not parse to the given parts"),
        ({"build_tag": (1, "-x")}, "does not parse to the given parts"),
        ({"build_tag": (1.5, "")}, "does not parse to the given parts"),
        ({"build_tag": (True, "")}, "does not parse to the given parts"),
        ({"variant": ""}, "invalid variant label ''"),
        ({"variant": "Bad-Label"}, "invalid build number 'py3'"),
        ({"variant": "x" * 17}, f"invalid variant label {'x' * 17!r}"),
        ({"tags": set()}, "invalid tag component '--'"),
        ({"tags": {Tag("py3", "none", "")}}, "invalid tag component 'py3-none-'"),
        ({"tags": {Tag("py3", "none", "a.b")}}, "does not parse to the given parts"),
        ({"tags": {Tag("py3", "none", "a-b")}}, "does not parse to the given parts"),
        ({"tags": {Tag("3py", "none", "any")}}, "invalid tag component"),
        (
            {"tags": {Tag("py3", "none", "any"), Tag("cp314", "cp314", "win_amd64")}},
            "does not parse to the given parts",
        ),
    ],
)
def test_normalized_wheel_init_invalid(
    kwargs: dict[str, typing.Any], error_message: str
) -> None:
    tags = {Tag("py3", "none", "any")}
    args: dict[str, typing.Any] = {
        "name": "foo",
        "version": Version("1.0"),
        "tags": tags,
        **kwargs,
    }
    with pytest.raises(InvalidWheelFilename, match=re.escape(error_message)):
        NormalizedWheelFilename(**args)

    wf = NormalizedWheelFilename("foo", Version("1.0"), tags)
    with pytest.raises(InvalidWheelFilename, match=re.escape(error_message)):
        wf.__replace__(**kwargs)


@pytest.mark.parametrize(
    ("kwargs", "error_message"),
    [
        ({"name": "foo-bar"}, "does not split into the given parts"),
        ({"version": "1.0-1"}, "does not split into the given parts"),
        ({"tags": "py3-none"}, "wrong number of parts"),
        ({"tags": "py3-none-any-x"}, "does not split into the given parts"),
        ({"build_tag": ""}, "does not split into the given parts"),
        ({"build_tag": "abc"}, "does not split into the given parts"),
        ({"build_tag": "abc", "variant": "x"}, "invalid build number 'abc'"),
        ({"variant": "a-b"}, "invalid build number 'py3'"),
    ],
)
def test_wheel_init_invalid(kwargs: dict[str, typing.Any], error_message: str) -> None:
    args: dict[str, typing.Any] = {
        "name": "foo",
        "version": "1.0",
        "tags": "py3-none-any",
        **kwargs,
    }
    with pytest.raises(InvalidWheelFilename, match=re.escape(error_message)):
        WheelFilename(**args)

    wf = WheelFilename("foo", "1.0", "py3-none-any")
    with pytest.raises(InvalidWheelFilename, match=re.escape(error_message)):
        wf.__replace__(**kwargs)


def test_wheel_init_does_not_check_parts() -> None:
    wf = WheelFilename("foo#bar", "x", "PY3-none-any", build_tag="01", variant="X")
    assert wf.to_filename() == "foo#bar-x-01-PY3-none-any-X.whl"
    with pytest.raises(InvalidWheelFilename, match="invalid project name 'foo#bar'"):
        wf.normalize()


def test_parse_and_create_filename() -> None:
    filename = "numpy-1.23.3-cp310-cp310-manylinux_2_17_x86_64.manylinux2014_x86_64.whl"
    sorted_f = "numpy-1.23.3-cp310-cp310-manylinux2014_x86_64.manylinux_2_17_x86_64.whl"

    wf = WheelFilename.from_filename(filename)
    assert wf.to_filename() == filename
    assert wf.normalize().to_filename() == sorted_f


def test_wheel_replace() -> None:
    wf = WheelFilename.from_filename("Foo.Bar-01.0-1a-py3-none-any-x86_64_v3.whl")
    new = wf.__replace__(version="2.0", tags="cp314-cp314-win_amd64")
    assert str(new) == "Foo.Bar-2.0-1a-cp314-cp314-win_amd64-x86_64_v3.whl"
    assert new.name == "Foo.Bar"
    assert str(wf.__replace__(variant=None, build_tag=None)) == (
        "Foo.Bar-01.0-py3-none-any.whl"
    )
    assert str(wf.__replace__(build_tag="02")) == (
        "Foo.Bar-01.0-02-py3-none-any-x86_64_v3.whl"
    )
    with pytest.raises(TypeError, match="unexpected"):
        wf.__replace__(nope=1)  # type: ignore[call-arg]
    if sys.version_info >= (3, 13):
        assert copy.replace(wf, version="2.0") == wf.__replace__(version="2.0")


def test_normalized_wheel_replace() -> None:
    tags = {Tag("py3", "none", "any")}
    wf = NormalizedWheelFilename(
        "Foo", Version("1.0"), tags, build_tag=(1, "a"), variant="x86_64_v3"
    )
    new_tags = {Tag("cp314", "cp314", "win_amd64")}
    new = wf.__replace__(version=Version("2.0"), tags=new_tags)
    assert new == NormalizedWheelFilename(
        "foo", Version("2.0"), new_tags, build_tag=(1, "a"), variant="x86_64_v3"
    )
    assert wf.__replace__(name="Bar.Baz").name == "bar-baz"
    assert wf.__replace__(variant=None, build_tag=()).to_filename() == (
        "foo-1.0-py3-none-any.whl"
    )
    with pytest.raises(TypeError, match="unexpected"):
        wf.__replace__(nope=1)  # type: ignore[call-arg]


def test_legacy_name() -> None:
    # Parsing accepts names that the normalized constructor rejects.
    wf = WheelFilename.from_filename("_foo-1.0-py3-none-any.whl").normalize()
    assert wf.name == "-foo"
    assert wf.to_filename() == "_foo-1.0-py3-none-any.whl"
    assert pickle.loads(pickle.dumps(wf)) == wf
    with pytest.raises(InvalidWheelFilename, match="invalid project name '-foo'"):
        wf.__replace__(version=Version("2.0"))
    fn = SourceDistributionFilename.from_filename("_foo-1.0.tar.gz").normalize()
    assert fn.name == "-foo"
    assert pickle.loads(pickle.dumps(fn)) == fn
    with pytest.raises(InvalidSdistFilename, match="invalid project name '-foo'"):
        fn.__replace__(version=Version("2.0"))


def test_repr() -> None:
    wf = WheelFilename.from_filename("Foo.Bar-01.0-1abc-py3-none-any.whl")
    assert repr(wf) == "<WheelFilename('Foo.Bar-01.0-1abc-py3-none-any.whl')>"
    assert repr(wf.normalize()) == (
        "<NormalizedWheelFilename('foo_bar-1.0-1abc-py3-none-any.whl')>"
    )
    fn = SourceDistributionFilename.from_filename("Foo-01.0.zip")
    assert repr(fn) == "<SourceDistributionFilename('Foo-01.0.zip')>"
    assert repr(fn.normalize()) == ("<NormalizedSdistFilename('foo-1.0.tar.gz')>")


@pytest.mark.parametrize(
    ("kwargs", "error_message"),
    [
        ({"name": ""}, "empty project name"),
        ({"version": "1.0-1"}, "does not split into the given parts"),
        ({"extension": ".whl"}, "extension must be '.tar.gz' or '.zip'"),
    ],
)
def test_sdist_init_invalid(kwargs: dict[str, str], error_message: str) -> None:
    args = {"name": "foo", "version": "1.0", **kwargs}
    with pytest.raises(InvalidSdistFilename, match=re.escape(error_message)):
        SourceDistributionFilename(**args)

    fn = SourceDistributionFilename("foo", "1.0")
    with pytest.raises(InvalidSdistFilename, match=re.escape(error_message)):
        fn.__replace__(**kwargs)


@pytest.mark.parametrize(
    ("kwargs", "error_message"),
    [
        ({"name": ""}, "(invalid project name '')"),
        ({"name": "foo bar"}, "(invalid project name 'foo bar')"),
        ({"version": "1.0"}, "does not parse to the given parts"),
    ],
)
def test_normalized_sdist_init_invalid(
    kwargs: dict[str, typing.Any], error_message: str
) -> None:
    args: dict[str, typing.Any] = {"name": "foo", "version": Version("1.0"), **kwargs}
    with pytest.raises(InvalidSdistFilename, match=re.escape(error_message)):
        NormalizedSdistFilename(**args)

    fn = NormalizedSdistFilename("foo", Version("1.0"))
    with pytest.raises(InvalidSdistFilename, match=re.escape(error_message)):
        fn.__replace__(**kwargs)


def test_sdist_replace() -> None:
    fn = SourceDistributionFilename.from_filename("Foo-01.0.zip")
    assert str(fn.__replace__(version="2.0")) == "Foo-2.0.zip"
    assert str(fn.__replace__(name="Bar-Baz")) == "Bar-Baz-01.0.zip"
    assert str(fn.__replace__(extension=".tar.gz")) == "Foo-01.0.tar.gz"
    with pytest.raises(TypeError, match="unexpected"):
        fn.__replace__(tags="")  # type: ignore[call-arg]


def test_normalized_sdist_replace() -> None:
    fn = NormalizedSdistFilename("foo", Version("1.0"))
    two = fn.__replace__(version=Version("2.0"))
    assert two == NormalizedSdistFilename("foo", Version("2.0"))
    assert fn.__replace__(name="Bar.Baz").to_filename() == "bar_baz-1.0.tar.gz"
    with pytest.raises(TypeError, match="unexpected"):
        fn.__replace__(tags=())  # type: ignore[call-arg]


def test_wheel_eq_hash() -> None:
    wf = WheelFilename.from_filename("foo-1.0-1-py3-none-any.whl")
    assert wf == WheelFilename("foo", "1.0", "py3-none-any", build_tag="1")
    assert hash(wf) == hash(WheelFilename("foo", "1.0", "py3-none-any", build_tag="1"))
    # The parts are compared as written.
    assert wf != WheelFilename.from_filename("Foo-1.0-1-py3-none-any.whl")
    assert wf != WheelFilename.from_filename("foo-1.0-py3-none-any.whl")
    assert wf != "foo-1.0-1-py3-none-any.whl"
    assert wf != wf.normalize()


def test_normalized_wheel_eq_hash() -> None:
    tags = {Tag("py3", "none", "any")}
    one = Version("1.0")
    wf = NormalizedWheelFilename("foo", one, tags, build_tag=(1, ""))
    same = NormalizedWheelFilename("Foo", one, tags, build_tag=(1, ""))
    assert wf == same
    assert hash(wf) == hash(same)
    assert wf != NormalizedWheelFilename(
        "foo", Version("1.0.0"), tags, build_tag=(1, "")
    )
    assert wf != NormalizedWheelFilename("foo", one, tags)
    assert wf != NormalizedWheelFilename(
        "foo", one, tags, build_tag=(1, ""), variant="x86_64_v3"
    )
    assert wf != "foo-1.0-1-py3-none-any.whl"
    raw = WheelFilename.from_filename("Foo-01.0-01-PY3-none-any.whl")
    assert raw.normalize() == wf
    assert len({wf, raw.normalize()}) == 1


def test_sdist_eq_hash() -> None:
    fn = SourceDistributionFilename.from_filename("foo-1.0.tar.gz")
    assert fn == SourceDistributionFilename("foo", "1.0")
    assert hash(fn) == hash(SourceDistributionFilename("foo", "1.0"))
    # The parts are compared as written.
    assert fn != SourceDistributionFilename("Foo", "1.0")
    assert fn != SourceDistributionFilename("foo", "1.0", extension=".zip")
    assert fn != "foo-1.0.tar.gz"
    assert fn != fn.normalize()


def test_normalized_sdist_eq_hash() -> None:
    fn = NormalizedSdistFilename("foo", Version("1.0"))
    same = NormalizedSdistFilename("Foo", Version("01.0"))
    assert fn == same
    assert hash(fn) == hash(same)
    assert fn != NormalizedSdistFilename("foo", Version("1.0.0"))
    assert fn == SourceDistributionFilename.from_filename("Foo-01.0.zip").normalize()
    assert fn != "foo-1.0.tar.gz"
    tags = {Tag("py3", "none", "any")}
    assert fn != NormalizedWheelFilename("foo", Version("1.0"), tags)


WHEELS = [
    "foo-1.0-py3-none-any.whl",
    "Foo.Bar-01.0-01abc-py3.py2-none-any-x86_64_v3.whl",
    "_foo.-1.0-py3-none-any.whl",
]
SDISTS = ["foo-1.0.tar.gz", "-foo--01.0.zip"]


@pytest.mark.parametrize(
    "raw",
    [
        *map(WheelFilename.from_filename, WHEELS),
        *map(SourceDistributionFilename.from_filename, SDISTS),
    ],
    ids=str,
)
@pytest.mark.parametrize("protocol", range(pickle.HIGHEST_PROTOCOL + 1))
def test_pickle(raw: WheelFilename | SourceDistributionFilename, protocol: int) -> None:
    for obj in (raw, raw.normalize()):
        loaded = pickle.loads(pickle.dumps(obj, protocol))
        assert loaded == obj
        assert hash(loaded) == hash(obj)
        assert str(loaded) == str(obj)
        assert copy.copy(obj) == obj
        assert copy.deepcopy(obj) == obj


def test_pickle_state() -> None:
    wf = WheelFilename.from_filename("Foo-01.0-1a-py3.py2-none-any-x86_64_v3.whl")
    assert wf.__getstate__() == "Foo-01.0-1a-py3.py2-none-any-x86_64_v3.whl"
    assert wf.normalize().__getstate__() == (
        "foo-1.0-1a-py2.py3-none-any-x86_64_v3.whl"
    )
    fn = SourceDistributionFilename.from_filename("Foo-01.0.zip")
    assert fn.__getstate__() == "Foo-01.0.zip"
    assert fn.normalize().__getstate__() == "foo-1.0.tar.gz"


@pytest.mark.parametrize(
    "cls",
    [
        WheelFilename,
        NormalizedWheelFilename,
        SourceDistributionFilename,
        NormalizedSdistFilename,
    ],
)
@pytest.mark.parametrize("state", [None, ("foo-1.0-py3-none-any.whl", None), 1])
def test_setstate_invalid(cls: type[typing.Any], state: object) -> None:
    obj = object.__new__(cls)
    with pytest.raises(TypeError, match=f"Cannot restore {cls.__name__}"):
        obj.__setstate__(state)


def test_setstate_invalid_filename() -> None:
    wf = WheelFilename.__new__(WheelFilename)
    with pytest.raises(InvalidWheelFilename):
        wf.__setstate__("foo-1.0.whl")
    nwf = NormalizedWheelFilename.__new__(NormalizedWheelFilename)
    with pytest.raises(InvalidWheelFilename):
        nwf.__setstate__("foo-x-py3-none-any.whl")
    fn = SourceDistributionFilename.__new__(SourceDistributionFilename)
    with pytest.raises(InvalidSdistFilename):
        fn.__setstate__("foo.tar.gz")
    nfn = NormalizedSdistFilename.__new__(NormalizedSdistFilename)
    with pytest.raises(InvalidSdistFilename):
        nfn.__setstate__("foo-x.tar.gz")


def test_strict_constructed() -> None:
    WheelFilename("foo", "1.0", "py3-none-any", build_tag="1").normalize(strict=True)
    SourceDistributionFilename("foo", "1.0").normalize(strict=True)
    wf = WheelFilename("Foo", "01.0", "py3-none-any", build_tag="01")
    with pytest.raises(ExceptionGroup) as wheel_info:
        wf.normalize(strict=True)
    assert [type(e) for e in wheel_info.value.exceptions] == [
        NonNormalizedName,
        NonNormalizedVersion,
        NonNormalizedBuildTag,
    ]
    assert wf.normalize().to_filename() == "foo-1.0-1-py3-none-any.whl"
    with pytest.raises(ExceptionGroup) as sdist_info:
        SourceDistributionFilename("Foo", "01.0").normalize(strict=True)
    assert [type(e) for e in sdist_info.value.exceptions] == [
        NonNormalizedName,
        NonNormalizedVersion,
    ]


def test_strict_after_replace() -> None:
    wf = WheelFilename.from_filename("Foo-01.0-py3-none-any.whl")
    with pytest.raises(ExceptionGroup):
        wf.__replace__(build_tag="1").normalize(strict=True)
    wf.__replace__(name="foo", version="1.0").normalize(strict=True)
    fn = SourceDistributionFilename.from_filename("Foo-01.0.zip")
    with pytest.raises(ExceptionGroup):
        fn.__replace__(name="foo", version="1.0").normalize(strict=True)
    fn.__replace__(name="foo", version="1.0", extension=".tar.gz").normalize(
        strict=True
    )


def test_strict_after_pickle() -> None:
    wf = WheelFilename.from_filename("Foo-01.0-py3-none-any.whl")
    with pytest.raises(ExceptionGroup):
        pickle.loads(pickle.dumps(wf)).normalize(strict=True)
    fn = SourceDistributionFilename.from_filename("Foo-01.0.tar.gz")
    with pytest.raises(ExceptionGroup):
        pickle.loads(pickle.dumps(fn)).normalize(strict=True)


@pytest.mark.parametrize("module", ["filenames", "utils"])
def test_import_order(module: str) -> None:
    code = f"import packaging.{module}; import packaging.filenames, packaging.utils"
    subprocess.run([sys.executable, "-c", code], check=True)


def test_raw_parts() -> None:
    wf = WheelFilename.from_filename("Foo.Bar-01.0-01-PY3-none-any-x86_64_v3.whl")
    assert wf.name == "Foo.Bar"
    assert wf.version == "01.0"
    assert wf.build_tag == "01"
    assert wf.tags == "PY3-none-any"
    assert wf.variant == "x86_64_v3"
    assert WheelFilename.from_filename("foo-1.0-py3-none-any.whl").build_tag is None

    fn = SourceDistributionFilename.from_filename("Foo-Bar-01.0.zip")
    assert fn.name == "Foo-Bar"
    assert fn.version == "01.0"
    assert fn.extension == ".zip"


def test_match_args() -> None:
    wf = WheelFilename.from_filename("Foo-1.0-py3-none-any.whl")
    assert WheelFilename.__match_args__ == ("name", "version", "tags")
    assert NormalizedWheelFilename.__match_args__ == ("name", "version", "tags")
    assert [getattr(wf, a) for a in wf.__match_args__] == ["Foo", "1.0", "py3-none-any"]
    assert SourceDistributionFilename.__match_args__ == ("name", "version")
    assert NormalizedSdistFilename.__match_args__ == ("name", "version")


def test_strict_message_gives_normalized_filename() -> None:
    wf = WheelFilename.from_filename("Foo.Bar-01.0-01-py3.py2-none-any.whl")
    with pytest.raises(ExceptionGroup) as e:
        wf.normalize(strict=True)
    assert e.value.message == (
        "Non-normalized wheel filename: 'Foo.Bar-01.0-01-py3.py2-none-any.whl', "
        "should be 'foo_bar-1.0-1-py2.py3-none-any.whl'"
    )

    fn = SourceDistributionFilename.from_filename("Foo-Bar-01.0.zip")
    with pytest.raises(ExceptionGroup) as e:
        fn.normalize(strict=True)
    assert e.value.message == (
        "Non-normalized sdist filename: 'Foo-Bar-01.0.zip', "
        "should be 'foo_bar-1.0.tar.gz'"
    )
