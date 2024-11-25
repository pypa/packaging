import pytest

from packaging.filenames import (
    Filename,
    InvalidFilename,
    InvalidWheelFilename,
    SourceFilename,
    WheelFilename,
)
from packaging.tags import Tag
from packaging.version import Version


def test_generic_from_filename_bad_extension():
    with pytest.raises(InvalidFilename) as e:
        Filename.from_filename("something.wrong")

    assert str(e.value) == (
        "Invalid filename (extension must be '.whl' or '.tar.gz'): 'something.wrong'"
    )


@pytest.mark.parametrize(
    "filename", ["sample_project-4.0.0.tar.gz", "sample_project-4.0.0-py3-none-any.whl"]
)
def test_generic_from_filename_passes(filename):
    fn = Filename.from_filename(filename)
    assert fn.name == fn.original_name == "sample_project"
    assert str(fn.version) == str(fn.original_version) == "4.0.0"


def test_initialize_generic_filename_unimplemented():
    with pytest.raises(NotImplementedError):
        Filename()


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
def test_sdist_not_strict_passes(name, version, expected_filename):
    fn = SourceFilename(name, version, strict=False)
    assert str(fn) == expected_filename
    assert fn.original_name == name
    assert fn.original_version == version


@pytest.mark.parametrize(
    ("filename", "error_message"),
    [
        (
            "bad.extension",  # Bad extension
            "Invalid filename (extension must be '.tar.gz')",
        ),
        (
            "extra-hyphens-1.0-9.tar.gz",  # Extra hyphens
            "Invalid filename (name and version parts can not contain hyphens)",
        ),
        (
            "no_hyphen.tar.gz",  # No hyphen
            "Invalid filename (hyphen must separate name and version parts)",
        ),
        (
            ".invalid.name-1.0.tar.gz",  # Name is not valid
            "Invalid filename (invalid project name '.invalid.name')",
        ),
        (
            "invalid.name-1.0.tar.gz",  # Name is not canonical (punctuation)
            "Invalid filename (non-normalized project name 'invalid.name')",
        ),
        (
            "invalid__name-1.0.tar.gz",  # Name is not canonical (punctuation)
            "Invalid filename (non-normalized project name 'invalid__name')",
        ),
        (
            "INVALID_NAME-1.0.tar.gz",  # Name is not canonical (casing)
            "Invalid filename (non-normalized project name 'INVALID_NAME')",
        ),
        (
            "valid_name-badversion.tar.gz",  # Version is not valid
            "Invalid filename (invalid version 'badversion')",
        ),
        (
            "valid_name-01.0.tar.gz",  # Version is not canonical
            "Invalid filename (non-normalized version '01.0')",
        ),
    ],
)
def test_sdist_from_filename_invalid(filename, error_message):
    with pytest.raises(InvalidFilename) as e:
        SourceFilename.from_filename(filename)

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
            "some_package",
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
def test_wheel_from_filename(filename, name, version, build_tag, tags):
    fn = WheelFilename.from_filename(filename)
    assert fn.name == name
    assert fn.version == version
    assert fn.build_tag == build_tag
    assert fn.tags == tags


@pytest.mark.parametrize(
    ("filename", "error_message"),
    [
        ("foo-1.0.whl", "Invalid filename (wrong number of parts)"),  # Missing tags
        (
            "foo-1.0-py3-none-any.wheel",  # Incorrect file extension (`.wheel`)
            "Invalid filename (extension must be '.whl')",
        ),
        (
            "foo__bar-1.0-py3-none-any.whl",  # Invalid name (`__`)
            "Invalid filename (invalid project name 'foo__bar')",
        ),
        (
            "foo#bar-1.0-py3-none-any.whl",  # Invalid name (`#`)
            "Invalid filename (invalid project name 'foo#bar')",
        ),
        (
            "foobar-1.x-py3-none-any.whl",  # Invalid version (`1.x`)
            "Invalid filename (invalid version '1.x')",
        ),
        (
            # Build number doesn't start with a digit (`abc`)
            "foo-1.0-abc-py3-none-any.whl",
            "Invalid filename (invalid build number 'abc')",
        ),
        (
            "foo-1.0-200-py3-none-any-junk.whl",  # Too many dashes (`-junk`)
            "Invalid filename (wrong number of parts)",
        ),
        (
            "fOo-1.0-py3-none-any.whl",  # Non-normalized project name
            "Invalid filename (non-normalized project name 'fOo')",
        ),
        (
            "foo-01.0-py3-none-any.whl",  # Non-normalized version
            "Invalid filename (non-normalized version '01.0')",
        ),
    ],
)
def test_wheel_from_filename_invalid(filename, error_message):
    with pytest.raises(InvalidWheelFilename) as e:
        WheelFilename.from_filename(filename)

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
def test_wheel_not_strict_passes(name, version, expected_filename):
    fn = WheelFilename(name, version, None, "py3", "none", "any", strict=False)
    assert str(fn) == expected_filename
    assert fn.original_name == name
    assert fn.original_version == version
