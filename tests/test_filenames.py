# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.

from __future__ import annotations

import copy
import pickle
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
    SourceDistributionFilename,
    UnsortedWheelTags,
    WheelFilename,
    validate_sdist_filename,
    validate_wheel_filename,
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
    fn = SourceDistributionFilename(name, version)
    assert fn.to_filename() == expected_filename
    assert str(fn) == expected_filename
    assert fn.name == canonicalize_name(name)
    assert fn.version == Version(version)
    validate_sdist_filename(expected_filename)
    assert SourceDistributionFilename.from_filename(expected_filename) == fn


@pytest.mark.parametrize(
    ("filename", "error_message", "error_type"),
    [
        (
            "bad.extension",  # Bad extension
            "Invalid sdist filename (extension must be '.tar.gz')",
            InvalidSdistFilename,
        ),
        (
            "foo-1.0.zip",  # Legacy extension
            "Invalid sdist filename (extension must be '.tar.gz')",
            InvalidSdistFilename,
        ),
        (
            "extra-hyphens-1.0-9.tar.gz",  # Extra hyphens
            "Invalid sdist filename (non-normalized project name 'extra-hyphens-1.0')",
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
            "Invalid sdist filename (non-normalized project name 'invalid.name')",
            NonNormalizedName,
        ),
        (
            "invalid__name-1.0.tar.gz",  # Name is not canonical (punctuation)
            "Invalid sdist filename (non-normalized project name 'invalid__name')",
            NonNormalizedName,
        ),
        (
            "INVALID_NAME-1.0.tar.gz",  # Name is not canonical (casing)
            "Invalid sdist filename (non-normalized project name 'INVALID_NAME')",
            NonNormalizedName,
        ),
        (
            "valid_name-badversion.tar.gz",  # Version is not valid
            "Invalid sdist filename (invalid version 'badversion')",
            InvalidSdistFilename,
        ),
        (
            "valid_name-01.0.tar.gz",  # Version is not canonical
            "Invalid sdist filename (non-normalized version '01.0')",
            NonNormalizedVersion,
        ),
    ],
)
def test_validate_sdist_filename_invalid(
    filename: str, error_message: str, error_type: type[InvalidFilename]
) -> None:
    with pytest.raises((InvalidFilename, ExceptionGroup)) as e:
        validate_sdist_filename(filename)

    if isinstance(e.value, ExceptionGroup):
        assert e.value.message == f"Non-normalized sdist filename: {filename!r}"
        (error,) = e.value.exceptions
    else:
        error = e.value
    assert type(error) is error_type
    assert str(error) == f"{error_message}: {filename!r}"


def test_validate_sdist_filename_multiple_errors() -> None:
    with pytest.raises(ExceptionGroup) as e:
        validate_sdist_filename("Foo-01.0.tar.gz")

    assert [type(error) for error in e.value.exceptions] == [
        NonNormalizedName,
        NonNormalizedVersion,
    ]


def test_sdist_from_filename_invalid_extension() -> None:
    with pytest.raises(InvalidSdistFilename) as e:
        SourceDistributionFilename.from_filename("foo-1.0.tgz")
    assert str(e.value) == (
        "Invalid sdist filename (extension must be '.tar.gz' or '.zip'): 'foo-1.0.tgz'"
    )


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
    validate_wheel_filename(filename)
    fn = WheelFilename.from_filename(filename)
    assert fn.name == name
    assert fn.version == version
    assert fn.build_tag == build_tag
    assert fn.tags == tags
    assert fn.variant is None
    assert fn.to_filename() == filename


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
    validate_wheel_filename(filename)
    fn = WheelFilename.from_filename(filename)
    assert fn.name == name
    assert fn.build_tag == build_tag
    assert fn.tags == tags
    assert fn.variant == variant
    assert fn.to_filename() == filename


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
            "Invalid wheel filename (non-normalized project name 'fOo')",
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
            "Invalid wheel filename (non-normalized version '01.0')",
            NonNormalizedVersion,
        ),
        (
            "foo-1.0-01-py3-none-any.whl",  # Non-normalized build tag
            "Invalid wheel filename (non-normalized build tag '01')",
            NonNormalizedBuildTag,
        ),
        (  # Unsorted interpreter tags (py3 before py2)
            "foo-1.0-py3.py2-none-any.whl",
            "Invalid wheel filename (compressed tag set components must be in "
            "sorted order per PEP 425)",
            UnsortedWheelTags,
        ),
        (
            # Unsorted platform tags (manylinux_ before manylinux2014)
            "numpy-1.23.3-cp310-cp310-manylinux_2_17_x86_64.manylinux2014_x86_64.whl",
            "Invalid wheel filename (compressed tag set components must be in "
            "sorted order per PEP 425)",
            UnsortedWheelTags,
        ),
        (  # Duplicate interpreter tags
            "foo-1.0-py3.py3-none-any.whl",
            "Invalid wheel filename (non-normalized tags 'py3.py3-none-any')",
            NonNormalizedTags,
        ),
    ],
)
def test_validate_wheel_filename_invalid(
    filename: str, error_message: str, error_type: type[InvalidFilename]
) -> None:
    with pytest.raises((InvalidFilename, ExceptionGroup)) as e:
        validate_wheel_filename(filename)

    if isinstance(e.value, ExceptionGroup):
        assert e.value.message == f"Non-normalized wheel filename: {filename!r}"
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
def test_validate_wheel_filename_multiple_errors(
    filename: str, error_types: list[type[InvalidFilename]]
) -> None:
    with pytest.raises(ExceptionGroup) as e:
        validate_wheel_filename(filename)

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
def test_wheel_init(
    name: str,
    version: str,
    build_tag: BuildTag,
    tags: set[Tag] | None,
    expected_filename: str,
) -> None:
    fn = WheelFilename(name, version, tags or {Tag("py3", "none", "any")}, build_tag)
    assert fn.to_filename() == expected_filename
    assert str(fn) == expected_filename
    assert fn.name == canonicalize_name(name)
    assert fn.version == Version(version)
    validate_wheel_filename(expected_filename)
    assert WheelFilename.from_filename(expected_filename) == fn


def test_parse_and_create_filename() -> None:
    filename = "numpy-1.23.3-cp310-cp310-manylinux_2_17_x86_64.manylinux2014_x86_64.whl"
    sorted_f = "numpy-1.23.3-cp310-cp310-manylinux2014_x86_64.manylinux_2_17_x86_64.whl"

    wf = WheelFilename.from_filename(filename)
    composed = wf.to_filename()
    assert sorted_f == composed


@pytest.mark.parametrize(
    ("kwargs", "error_message"),
    [
        ({"name": ""}, "invalid project name ''"),
        ({"name": "foo bar!"}, "invalid project name 'foo bar!'"),
        ({"name": "_foo"}, "invalid project name '_foo'"),
        ({"version": "not-a-version"}, "invalid version 'not-a-version'"),
        ({"build_tag": (-1, "")}, "invalid build tag (-1, '')"),
        ({"build_tag": (1, "2")}, "invalid build tag (1, '2')"),
        ({"build_tag": (1, "-x")}, "invalid build tag (1, '-x')"),
        ({"build_tag": (1.5, "")}, "invalid build tag (1.5, '')"),
        ({"build_tag": (True, "")}, "invalid build tag (True, '')"),
        ({"variant": ""}, "invalid variant label ''"),
        ({"variant": "Bad-Label"}, "invalid variant label 'Bad-Label'"),
        ({"variant": "x" * 17}, f"invalid variant label {'x' * 17!r}"),
        ({"tags": set()}, "the tag set must have at least one tag"),
        ({"tags": {Tag("py3", "none", "")}}, "invalid tag 'py3-none-'"),
        ({"tags": {Tag("py3", "none", "a.b")}}, "invalid tag 'py3-none-a.b'"),
        ({"tags": {Tag("py3", "none", "a-b")}}, "invalid tag 'py3-none-a-b'"),
        ({"tags": {Tag("3py", "none", "any")}}, "invalid tag '3py-none-any'"),
        (
            {"tags": {Tag("py3", "none", "any"), Tag("cp314", "cp314", "win_amd64")}},
            "the tag set cannot be compressed, it must contain every combination: "
            "['cp314-cp314-win_amd64', 'py3-none-any']",
        ),
    ],
)
def test_wheel_init_invalid(kwargs: dict[str, typing.Any], error_message: str) -> None:
    tags = {Tag("py3", "none", "any")}
    args: dict[str, typing.Any] = {
        "name": "foo",
        "version": "1.0",
        "tags": tags,
        **kwargs,
    }
    with pytest.raises(InvalidWheelFilename) as e:
        WheelFilename(**args)
    assert str(e.value) == f"Invalid wheel filename ({error_message})"

    wf = WheelFilename("foo", "1.0", tags)
    with pytest.raises(InvalidWheelFilename) as e:
        wf.__replace__(**kwargs)
    assert str(e.value) == f"Invalid wheel filename ({error_message})"


def test_copy_returns_self() -> None:
    wf = WheelFilename("foo", "1.0", {Tag("py3", "none", "any")})
    assert copy.copy(wf) is wf
    assert copy.deepcopy(wf) is wf
    fn = SourceDistributionFilename("foo", "1.0")
    assert copy.copy(fn) is fn
    assert copy.deepcopy(fn) is fn


def test_replace_does_not_reparse(monkeypatch: pytest.MonkeyPatch) -> None:
    wf = WheelFilename("foo", "1.0", {Tag("py3", "none", "any")})
    fn = SourceDistributionFilename("foo", "1.0")
    monkeypatch.setattr(WheelFilename, "from_filename", None)
    monkeypatch.setattr(SourceDistributionFilename, "from_filename", None)
    assert wf.__replace__(version="2.0").version == Version("2.0")
    assert fn.__replace__(version="2.0").version == Version("2.0")


def test_wheel_replace() -> None:
    tags = {Tag("py3", "none", "any")}
    wf = WheelFilename("Foo", "1.0", tags, (1, "a"), "x86_64_v3")
    new = wf.__replace__(version="2.0", tags={Tag("cp314", "cp314", "win_amd64")})
    assert new == WheelFilename(
        "Foo", "2.0", {Tag("cp314", "cp314", "win_amd64")}, (1, "a"), "x86_64_v3"
    )
    assert new.name == "foo"
    assert wf.__replace__(version=Version("2.0")) == wf.__replace__(version="2.0")
    assert wf.__replace__(variant=None, build_tag=()).to_filename() == (
        "foo-1.0-py3-none-any.whl"
    )
    with pytest.raises(TypeError, match="unexpected"):
        wf.__replace__(nope=1)  # type: ignore[call-arg]


def test_legacy_name_from_filename() -> None:
    # Parsing accepts names that the constructor rejects.
    wf = WheelFilename.from_filename("_foo-1.0-py3-none-any.whl")
    assert wf.name == "-foo"
    assert wf.__replace__(version="2.0").to_filename() == "_foo-2.0-py3-none-any.whl"
    fn = SourceDistributionFilename.from_filename("_foo-1.0.tar.gz")
    assert fn.__replace__(version="2.0").to_filename() == "_foo-2.0.tar.gz"


def test_wheel_repr() -> None:
    tags = frozenset({Tag("py3", "none", "any")})
    wf = WheelFilename("Foo.Bar", "01.0", tags, (1, "abc"))
    assert repr(wf) == (
        f"WheelFilename(name='foo-bar', version='1.0', tags={tags!r}, "
        "build_tag=(1, 'abc'), variant=None)"
    )


@pytest.mark.parametrize(
    ("kwargs", "error_message"),
    [
        ({"name": ""}, "invalid project name ''"),
        ({"name": "foo bar"}, "invalid project name 'foo bar'"),
        ({"version": "not-a-version"}, "invalid version 'not-a-version'"),
    ],
)
def test_sdist_init_invalid(kwargs: dict[str, str], error_message: str) -> None:
    args = {"name": "foo", "version": "1.0", **kwargs}
    with pytest.raises(InvalidSdistFilename) as e:
        SourceDistributionFilename(**args)
    assert str(e.value) == f"Invalid sdist filename ({error_message})"

    fn = SourceDistributionFilename("foo", "1.0")
    with pytest.raises(InvalidSdistFilename) as e:
        fn.__replace__(**kwargs)
    assert str(e.value) == f"Invalid sdist filename ({error_message})"


def test_sdist_replace() -> None:
    fn = SourceDistributionFilename("foo", "1.0")
    assert fn.__replace__(version="2.0") == SourceDistributionFilename("foo", "2.0")
    assert fn.__replace__(name="bar") == SourceDistributionFilename("bar", "1.0")
    with pytest.raises(TypeError, match="unexpected"):
        fn.__replace__(tags=())  # type: ignore[call-arg]


def test_sdist_repr() -> None:
    fn = SourceDistributionFilename("Foo", Version("1.0"))
    assert repr(fn) == "SourceDistributionFilename(name='foo', version='1.0')"


def test_wheel_eq_hash() -> None:
    tags = {Tag("py3", "none", "any")}
    wf = WheelFilename("foo", "1.0", tags, (1, ""))
    assert wf == WheelFilename("foo", "1.0", tags, (1, ""))
    assert hash(wf) == hash(WheelFilename("foo", "1.0", tags, (1, "")))
    assert wf == WheelFilename("Foo", "1.0", tags, (1, ""))
    assert hash(wf) == hash(WheelFilename("Foo", "1.0", tags, (1, "")))
    assert wf != WheelFilename("foo", "1.0.0", tags, (1, ""))
    assert wf != WheelFilename("foo", "1.0", tags)
    assert wf != WheelFilename("foo", "1.0", tags, (1, ""), "x86_64_v3")
    assert wf != "foo-1.0-1-py3-none-any.whl"
    assert len({wf, WheelFilename.from_filename(str(wf))}) == 1
    raw = WheelFilename.from_filename("Foo.Bar-01.0-1-py3-none-any.whl")
    assert raw == WheelFilename("foo_bar", "1.0", tags, (1, ""))


def test_sdist_eq_hash() -> None:
    fn = SourceDistributionFilename("foo", "1.0")
    assert fn == SourceDistributionFilename("foo", "1.0")
    assert hash(fn) == hash(SourceDistributionFilename("foo", "1.0"))
    assert fn != SourceDistributionFilename("foo", "1.0.0")
    assert fn == SourceDistributionFilename("Foo", "01.0")
    assert hash(fn) == hash(SourceDistributionFilename("Foo", "01.0"))
    assert fn == SourceDistributionFilename.from_filename("foo-1.0.zip")
    assert fn != "foo-1.0.tar.gz"
    assert fn != WheelFilename("foo", "1.0", {Tag("py3", "none", "any")})


@pytest.mark.parametrize(
    "wf",
    [
        WheelFilename("foo", "1.0", tags={Tag("py3", "none", "any")}),
        WheelFilename(
            "foo",
            "1.0",
            {Tag("py2", "none", "any"), Tag("py3", "none", "any")},
            (1, "abc"),
            "x86_64_v3",
        ),
        WheelFilename.from_filename("_foo.-1.0-py3-none-any.whl"),
    ],
)
@pytest.mark.parametrize("protocol", range(pickle.HIGHEST_PROTOCOL + 1))
def test_wheel_pickle(wf: WheelFilename, protocol: int) -> None:
    loaded = pickle.loads(pickle.dumps(wf, protocol))
    assert loaded == wf
    assert hash(loaded) == hash(wf)


def test_wheel_pickle_state() -> None:
    tags = {Tag("py3", "none", "any"), Tag("py2", "none", "any")}
    wf = WheelFilename("Foo", "01.0", tags, (1, "a"), "x86_64_v3")
    state = "foo-1.0-1a-py2.py3-none-any-x86_64_v3.whl"
    assert wf.__getstate__() == state
    loaded = WheelFilename.__new__(WheelFilename)
    loaded.__setstate__(state)
    assert loaded == wf


@pytest.mark.parametrize("state", [None, ("foo", "1.0", ("py3-none-any",), (), None)])
def test_wheel_setstate_invalid(state: object) -> None:
    wf = WheelFilename.__new__(WheelFilename)
    with pytest.raises(TypeError, match="Cannot restore WheelFilename"):
        wf.__setstate__(state)


def test_wheel_setstate_invalid_filename() -> None:
    wf = WheelFilename.__new__(WheelFilename)
    with pytest.raises(InvalidWheelFilename):
        wf.__setstate__("foo-1.0.whl")


@pytest.mark.parametrize(
    "fn",
    [
        SourceDistributionFilename("foo", "1.0"),
        SourceDistributionFilename.from_filename("-foo--01.0.tar.gz"),
    ],
)
@pytest.mark.parametrize("protocol", range(pickle.HIGHEST_PROTOCOL + 1))
def test_sdist_pickle(fn: SourceDistributionFilename, protocol: int) -> None:
    loaded = pickle.loads(pickle.dumps(fn, protocol))
    assert loaded == fn
    assert repr(loaded) == repr(fn)
    assert hash(loaded) == hash(fn)


def test_sdist_pickle_state() -> None:
    fn = SourceDistributionFilename("Foo", "01.0")
    assert fn.__getstate__() == "foo-1.0.tar.gz"
    loaded = SourceDistributionFilename.__new__(SourceDistributionFilename)
    loaded.__setstate__("foo-1.0.tar.gz")
    assert loaded == fn


@pytest.mark.parametrize("state", [None, ("foo", "1.0")])
def test_sdist_setstate_invalid(state: object) -> None:
    fn = SourceDistributionFilename.__new__(SourceDistributionFilename)
    with pytest.raises(TypeError, match="Cannot restore SourceDistributionFilename"):
        fn.__setstate__(state)


def test_sdist_setstate_invalid_filename() -> None:
    fn = SourceDistributionFilename.__new__(SourceDistributionFilename)
    with pytest.raises(InvalidSdistFilename):
        fn.__setstate__("foo-x.tar.gz")


@pytest.mark.parametrize("module", ["filenames", "utils"])
def test_import_order(module: str) -> None:
    code = f"import packaging.{module}; import packaging.filenames, packaging.utils"
    subprocess.run([sys.executable, "-c", code], check=True)
