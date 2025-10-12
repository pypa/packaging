from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
import tomli_w

from packaging.markers import Marker
from packaging.pylock import (
    Package,
    PackageDirectory,
    PackageVcs,
    PackageWheel,
    Pylock,
    PylockRequiredKeyError,
    PylockUnsupportedVersionError,
    PylockValidationError,
    is_valid_pylock_path,
)
from packaging.specifiers import SpecifierSet
from packaging.utils import NormalizedName
from packaging.version import Version

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


@pytest.mark.parametrize(
    "file_name,valid",
    [
        ("pylock.toml", True),
        ("pylock.spam.toml", True),
        ("pylock.json", False),
        ("pylock..toml", False),
    ],
)
def test_pylock_file_name(file_name: str, valid: bool) -> None:
    assert is_valid_pylock_path(Path(file_name)) is valid


def test_toml_roundtrip() -> None:
    pep751_example = (
        Path(__file__).parent / "pylock" / "pylock.spec-example.toml"
    ).read_text()
    pylock_dict = tomllib.loads(pep751_example)
    pylock = Pylock.from_dict(pylock_dict)
    # Check that the roundrip via Pylock dataclasses produces the same TOML
    # output, modulo TOML serialization differences.
    assert tomli_w.dumps(pylock.to_dict()) == tomli_w.dumps(pylock_dict)


@pytest.mark.parametrize("version", ["1.0", "1.1"])
def test_pylock_version(version: str) -> None:
    data = {
        "lock-version": version,
        "created-by": "pip",
        "packages": [],
    }
    Pylock.from_dict(data)


@pytest.mark.parametrize("version", ["0.9", "2", "2.0", "2.1"])
def test_pylock_unsupported_version(version: str) -> None:
    data = {
        "lock-version": version,
        "created-by": "pip",
        "packages": [],
    }
    with pytest.raises(PylockUnsupportedVersionError):
        Pylock.from_dict(data)


def test_pylock_invalid_version() -> None:
    data = {
        "lock-version": "2.x",
        "created-by": "pip",
        "packages": [],
    }
    with pytest.raises(PylockValidationError) as exc_info:
        Pylock.from_dict(data)
    assert str(exc_info.value) == "Invalid version: '2.x' in 'lock-version'"


def test_pylock_unexpected_type() -> None:
    data = {
        "lock-version": 1.0,
        "created-by": "pip",
        "packages": [],
    }
    with pytest.raises(PylockValidationError) as exc_info:
        Pylock.from_dict(data)
    assert str(exc_info.value) == (
        "Unexpected type float (expected str) in 'lock-version'"
    )


def test_pylock_missing_version() -> None:
    data = {
        "created-by": "pip",
        "packages": [],
    }
    with pytest.raises(PylockRequiredKeyError) as exc_info:
        Pylock.from_dict(data)
    assert str(exc_info.value) == "Missing required value in 'lock-version'"


def test_pylock_missing_created_by() -> None:
    data = {
        "lock-version": "1.0",
        "packages": [],
    }
    with pytest.raises(PylockRequiredKeyError) as exc_info:
        Pylock.from_dict(data)
    assert str(exc_info.value) == "Missing required value in 'created-by'"


def test_pylock_missing_packages() -> None:
    data = {
        "lock-version": "1.0",
        "created-by": "uv",
    }
    with pytest.raises(PylockRequiredKeyError) as exc_info:
        Pylock.from_dict(data)
    assert str(exc_info.value) == "Missing required value in 'packages'"


def test_pylock_packages_without_dist() -> None:
    data = {
        "lock-version": "1.0",
        "created-by": "pip",
        "packages": [{"name": "example", "version": "1.0"}],
    }
    with pytest.raises(PylockValidationError) as exc_info:
        Pylock.from_dict(data)
    assert str(exc_info.value) == (
        "Exactly one of vcs, directory, archive must be set "
        "if sdist and wheels are not set "
        "in 'packages[0]'"
    )


def test_pylock_packages_with_dist_and_archive() -> None:
    data = {
        "lock-version": "1.0",
        "created-by": "pip",
        "packages": [
            {
                "name": "example",
                "version": "1.0",
                "archive": {
                    "path": "example.tar.gz",
                    "hashes": {"sha256": "f" * 40},
                },
                "sdist": {
                    "path": "example.tar.gz",
                    "hashes": {"sha256": "f" * 40},
                },
            }
        ],
    }
    with pytest.raises(PylockValidationError) as exc_info:
        Pylock.from_dict(data)
    assert str(exc_info.value) == (
        "None of vcs, directory, archive must be set "
        "if sdist or wheels are set "
        "in 'packages[0]'"
    )


def test_pylock_packages_with_archive_directory_and_vcs() -> None:
    data = {
        "lock-version": "1.0",
        "created-by": "pip",
        "packages": [
            {
                "name": "example",
                "version": "1.0",
                "archive": {
                    "path": "example.tar.gz",
                    "hashes": {"sha256": "f" * 40},
                },
                "vcs": {
                    "type": "git",
                    "url": "https://githhub/pypa/packaging",
                    "commit-id": "...",
                },
                "directory": {
                    "path": ".",
                    "editable": False,
                },
            }
        ],
    }
    with pytest.raises(PylockValidationError) as exc_info:
        Pylock.from_dict(data)
    assert str(exc_info.value) == (
        "Exactly one of vcs, directory, archive must be set "
        "if sdist and wheels are not set "
        "in 'packages[0]'"
    )


def test_pylock_basic_package() -> None:
    data = {
        "lock-version": "1.0",
        "created-by": "pip",
        "requires-python": ">=3.10",
        "environments": ['os_name == "posix"'],
        "packages": [
            {
                "name": "example",
                "version": "1.0",
                "marker": 'os_name == "posix"',
                "requires-python": "!=3.10.1,>=3.10",
                "directory": {
                    "path": ".",
                    "editable": False,
                },
            }
        ],
    }
    pylock = Pylock.from_dict(data)
    assert pylock.environments == [Marker('os_name == "posix"')]
    package = pylock.packages[0]
    assert package.version == Version("1.0")
    assert package.marker == Marker('os_name == "posix"')
    assert package.requires_python == SpecifierSet(">=3.10, !=3.10.1")
    assert pylock.to_dict() == data


def test_pylock_vcs_package() -> None:
    data = {
        "lock-version": "1.0",
        "created-by": "pip",
        "packages": [
            {
                "name": "packaging",
                "vcs": {
                    "type": "git",
                    "url": "https://githhub/pypa/packaging",
                    "commit-id": "...",
                },
            }
        ],
    }
    pylock = Pylock.from_dict(data)
    assert pylock.to_dict() == data


def test_pylock_invalid_archive() -> None:
    data = {
        "lock-version": "1.0",
        "created-by": "pip",
        "requires-python": ">=3.10",
        "environments": ['os_name == "posix"'],
        "packages": [
            {
                "name": "example",
                "archive": {
                    # "path": "example.tar.gz",
                    "hashes": {"sha256": "f" * 40},
                },
            }
        ],
    }
    with pytest.raises(PylockValidationError) as exc_info:
        Pylock.from_dict(data)
    assert str(exc_info.value) == (
        "path or url must be provided in 'packages[0].archive'"
    )


def test_pylock_invalid_vcs() -> None:
    with pytest.raises(PylockValidationError) as exc_info:
        PackageVcs._from_dict({"type": "git", "commit-id": "f" * 40})
    assert str(exc_info.value) == "path or url must be provided"


def test_pylock_invalid_wheel() -> None:
    data = {
        "lock-version": "1.0",
        "created-by": "pip",
        "requires-python": ">=3.10",
        "environments": ['os_name == "posix"'],
        "packages": [
            {
                "name": "example",
                "wheels": [
                    {
                        "name": "example-1.0-py3-none-any.whl",
                        "path": "./example-1.0-py3-none-any.whl",
                        # Purposefully no "hashes" key.
                    }
                ],
            }
        ],
    }
    with pytest.raises(PylockValidationError) as exc_info:
        Pylock.from_dict(data)
    assert str(exc_info.value) == (
        "Missing required value in 'packages[0].wheels[0].hashes'"
    )


def test_pylock_invalid_environments() -> None:
    data = {
        "lock-version": "1.0",
        "created-by": "pip",
        "environments": [
            'os_name == "posix"',
            'invalid_marker == "..."',
        ],
        "packages": [],
    }
    with pytest.raises(PylockValidationError) as exc_info:
        Pylock.from_dict(data)
    assert str(exc_info.value) == (
        "Expected a marker variable or quoted string\n"
        '    invalid_marker == "..."\n'
        "    ^ "
        "in 'environments[1]'"
    )


def test_pylock_invalid_environments_type() -> None:
    data = {
        "lock-version": "1.0",
        "created-by": "pip",
        "environments": [
            'os_name == "posix"',
            1,
        ],
        "packages": [],
    }
    with pytest.raises(PylockValidationError) as exc_info:
        Pylock.from_dict(data)
    assert str(exc_info.value) == (
        "Unexpected type int (expected str) in 'environments[1]'"
    )


def test_pylock_extras_and_groups() -> None:
    data = {
        "lock-version": "1.0",
        "created-by": "pip",
        "extras": ["feat1", "feat2"],
        "dependency-groups": ["dev", "docs"],
        "default-groups": ["dev"],
        "packages": [],
    }
    pylock = Pylock.from_dict(data)
    assert pylock.extras == ["feat1", "feat2"]
    assert pylock.dependency_groups == ["dev", "docs"]
    assert pylock.default_groups == ["dev"]


def test_pylock_tool() -> None:
    data = {
        "lock-version": "1.0",
        "created-by": "pip",
        "packages": [
            {
                "name": "example",
                "sdist": {
                    "name": "example-1.0.tar.gz",
                    "path": "./example-1.0.tar.gz",
                    "upload-time": datetime(2023, 10, 1, 0, 0),
                    "hashes": {"sha256": "f" * 40},
                },
                "tool": {"pip": {"foo": "bar"}},
            }
        ],
        "tool": {"pip": {"version": "25.2"}},
    }
    pylock = Pylock.from_dict(data)
    assert pylock.tool == {"pip": {"version": "25.2"}}
    package = pylock.packages[0]
    assert package.tool == {"pip": {"foo": "bar"}}


def test_pylock_package_not_a_table() -> None:
    data = {
        "lock-version": "1.0",
        "created-by": "pip",
        "packages": ["example"],
    }
    with pytest.raises(PylockValidationError) as exc_info:
        Pylock.from_dict(data)
    assert str(exc_info.value) == (
        "Unexpected type str (expected Mapping) in 'packages[0]'"
    )


@pytest.mark.parametrize(
    "hashes,expected_error",
    [
        (
            {
                "sha256": "f" * 40,
                "md5": 1,
            },
            "Hash values must be strings in 'hashes'",
        ),
        (
            {},
            "At least one hash must be provided in 'hashes'",
        ),
        (
            "sha256:...",
            "Unexpected type str (expected Mapping) in 'hashes'",
        ),
    ],
)
def test_hash_validation(hashes: dict[str, Any], expected_error: str) -> None:
    with pytest.raises(PylockValidationError) as exc_info:
        PackageWheel._from_dict(
            dict(
                name="example-1.0-py3-none-any.whl",
                upload_time=None,
                url="https://example.com/example-1.0-py3-none-any.whl",
                path=None,
                size=None,
                hashes=hashes,
            )
        )
    assert str(exc_info.value) == expected_error


def test_package_name_validation() -> None:
    with pytest.raises(PylockValidationError) as exc_info:
        Package._from_dict({"name": "Example"})
    assert str(exc_info.value) == "Name 'Example' is not normalized in 'name'"


def test_extras_name_validation() -> None:
    with pytest.raises(PylockValidationError) as exc_info:
        Pylock.from_dict(
            {
                "lock-version": "1.0",
                "created-by": "pip",
                "extras": ["extra", "Feature"],
                "packages": [],
            }
        )
    assert str(exc_info.value) == "Name 'Feature' is not normalized in 'extras[1]'"


def test_is_direct() -> None:
    direct_package = Package(
        name=NormalizedName("example"),
        directory=PackageDirectory(path="."),
    )
    assert direct_package.is_direct
    wheel_package = Package(
        name=NormalizedName("example"),
        wheels=[
            PackageWheel(
                url="https://example.com/example-1.0-py3-none-any.whl",
                hashes={"sha256": "f" * 40},
            )
        ],
    )
    assert not wheel_package.is_direct


def test_validate() -> None:
    pylock = Pylock(
        lock_version=Version("1.0"),
        created_by="some_tool",
        packages=[
            Package(
                name=NormalizedName("example-package"),
                version=Version("1.0.0"),
                wheels=[
                    PackageWheel(
                        url="https://example.com/example_package-1.0.0-py3-none-any.whl",
                        hashes={"sha256": "0fd.."},
                    )
                ],
            )
        ],
    )
    pylock.validate()  # Should not raise any exceptions
    pylock = Pylock(
        lock_version=Version("1.0"),
        created_by="some_tool",
        packages=[
            Package(
                name=NormalizedName("example_package"),  # not normalized
                version=Version("1.0.0"),
                wheels=[
                    PackageWheel(
                        url="https://example.com/example_package-1.0.0-py3-none-any.whl",
                        hashes={"sha256": "0fd.."},
                    )
                ],
            )
        ],
    )
    with pytest.raises(PylockValidationError) as exc_info:
        pylock.validate()
    assert (
        str(exc_info.value)
        == "Name 'example_package' is not normalized in 'packages[0].name'"
    )


def test_validate_sequence_of_str() -> None:
    pylock = Pylock(
        lock_version=Version("1.0"),
        created_by="some_tool",
        packages=[],
        dependency_groups="abc",  # should be a sequence of str
    )
    with pytest.raises(PylockValidationError) as exc_info:
        pylock.validate()
    assert str(exc_info.value) == (
        "Unexpected type str (expected Sequence) in 'dependency-groups'"
    )
