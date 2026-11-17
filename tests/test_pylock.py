from __future__ import annotations

import copy
import datetime
import pickle
import sys
from pathlib import Path
from typing import Any

import pytest
import tomli_w

from packaging.markers import Marker
from packaging.pylock import (
    Package,
    PackageDirectory,
    PackageSdist,
    PackageVcs,
    PackageWheel,
    Pylock,
    PylockUnsupportedVersionError,
    PylockValidationError,
    is_valid_pylock_path,
)
from packaging.specifiers import SpecifierSet
from packaging.utils import NormalizedName
from packaging.version import Version

from .test_direct_url import _dict_state

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


@pytest.mark.parametrize(
    ("file_name", "valid"),
    [
        ("pylock.toml", True),
        ("pylock.spam.toml", True),
        ("pylock.json", False),
        ("pylock..toml", False),
        ("pylock.spam.toml\n", False),
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


@pytest.mark.parametrize(
    "version", ["0.9", "2", "2.0", "2.1", "2.0.dev0", "2.0a1", "2.0rc1"]
)
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


def test_pylock_bool_rejected_for_int() -> None:
    # TOML distinguishes booleans from integers, so a boolean must be rejected
    # where an integer is expected even though bool is a subclass of int.
    data = {
        "lock-version": "1.0",
        "created-by": "pip",
        "packages": [
            {
                "name": "example",
                "wheels": [
                    {
                        "name": "example-1.0-py3-none-any.whl",
                        "path": "./example-1.0-py3-none-any.whl",
                        "hashes": {"sha256": "f" * 40},
                        "size": True,
                    }
                ],
            }
        ],
    }
    with pytest.raises(PylockValidationError) as exc_info:
        Pylock.from_dict(data)
    assert str(exc_info.value) == (
        "Unexpected type bool (expected int) in 'packages[0].wheels[0].size'"
    )


def test_pylock_missing_version() -> None:
    data = {
        "created-by": "pip",
        "packages": [],
    }
    with pytest.raises(PylockValidationError) as exc_info:
        Pylock.from_dict(data)
    assert str(exc_info.value) == "Missing required value in 'lock-version'"


def test_pylock_missing_created_by() -> None:
    data = {
        "lock-version": "1.0",
        "packages": [],
    }
    with pytest.raises(PylockValidationError) as exc_info:
        Pylock.from_dict(data)
    assert str(exc_info.value) == "Missing required value in 'created-by'"


def test_pylock_missing_packages() -> None:
    data = {
        "lock-version": "1.0",
        "created-by": "uv",
    }
    with pytest.raises(PylockValidationError) as exc_info:
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
                    "path": "example-1.0.tar.gz",
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


@pytest.mark.parametrize(
    ("dist", "expected_filename"),
    [
        # sdists
        (
            PackageSdist(
                name="example-1.0.tar.gz",
                hashes={},
            ),
            "example-1.0.tar.gz",
        ),
        (
            PackageSdist(
                path="./example-1.0.tar.gz",
                hashes={},
            ),
            "example-1.0.tar.gz",
        ),
        (
            PackageSdist(
                path=".\\example-1.0.tar.gz",
                hashes={},
            ),
            "example-1.0.tar.gz",
        ),
        (
            PackageSdist(
                path="example-1.0.tar.gz",
                hashes={},
            ),
            "example-1.0.tar.gz",
        ),
        (
            PackageSdist(
                url="https://example.com/example-1.0.tar.gz",
                hashes={},
            ),
            "example-1.0.tar.gz",
        ),
        (
            # name preferred over path
            PackageSdist(
                name="example-2.0.tar.gz",
                path=".\\example-1.0.tar.gz",
                hashes={},
            ),
            "example-2.0.tar.gz",
        ),
        (
            # name preferred over url
            PackageSdist(
                name="example-2.0.tar.gz",
                url="https://example.com/example-1.0.tar.gz",
                hashes={},
            ),
            "example-2.0.tar.gz",
        ),
        (
            # path preferred over url
            PackageSdist(
                url="https://example.com/example-2.0.tar.gz",
                path="./example-1.0.tar.gz",
                hashes={},
            ),
            "example-1.0.tar.gz",
        ),
        # wheels
        (
            PackageWheel(
                name="example-1.0-py3-none-any.whl",
                hashes={},
            ),
            "example-1.0-py3-none-any.whl",
        ),
        (
            PackageWheel(
                path="./example-1.0-py3-none-any.whl",
                hashes={},
            ),
            "example-1.0-py3-none-any.whl",
        ),
        (
            PackageWheel(
                path=".\\example-1.0-py3-none-any.whl",
                hashes={},
            ),
            "example-1.0-py3-none-any.whl",
        ),
        (
            PackageWheel(
                path="example-1.0-py3-none-any.whl",
                hashes={},
            ),
            "example-1.0-py3-none-any.whl",
        ),
        (
            PackageWheel(
                url="https://example.com/example-1.0-py3-none-any.whl",
                hashes={},
            ),
            "example-1.0-py3-none-any.whl",
        ),
        (
            # percent-encoded url file name is decoded
            PackageWheel(
                url="https://example.com/example-2.12.1%2Bcu130-py3-none-any.whl",
                hashes={},
            ),
            "example-2.12.1+cu130-py3-none-any.whl",
        ),
        (
            # name preferred over path
            PackageWheel(
                name="example-2.0-py3-none-any.whl",
                path=".\\example-1.0-py3-none-any.whl",
                hashes={},
            ),
            "example-2.0-py3-none-any.whl",
        ),
        (
            # name preferred over url
            PackageWheel(
                name="example-2.0-py3-none-any.whl",
                url="https://example.com/example-1.0-py3-none-any.whl",
                hashes={},
            ),
            "example-2.0-py3-none-any.whl",
        ),
        (
            # path preferred over url
            PackageWheel(
                url="https://example.com/example-2.0-py3-none-any.whl",
                path="./example-1.0-py3-none-any.whl",
                hashes={},
            ),
            "example-1.0-py3-none-any.whl",
        ),
    ],
)
def test_dist_filename(
    dist: PackageSdist | PackageWheel, expected_filename: str
) -> None:
    assert dist.filename == expected_filename


@pytest.mark.parametrize(
    "directory", ["dist/files\\", "dist\\files/", "C:/dist\\", "C:\\dist/"]
)
@pytest.mark.parametrize(
    ("kind", "filename"),
    [("sdist", "example-1.0.tar.gz"), ("wheels", "example-1.0-py3-none-any.whl")],
)
def test_pylock_mixed_path_separators(directory: str, kind: str, filename: str) -> None:
    artifact = {"path": directory + filename, "hashes": {"sha256": "f" * 64}}
    data = {
        "lock-version": "1.0",
        "created-by": "pip",
        "packages": [
            {
                "name": "example",
                "version": "1.0",
                kind: [artifact] if kind == "wheels" else artifact,
            }
        ],
    }
    pylock = Pylock.from_dict(data)
    package = pylock.packages[0]
    dist = package.wheels[0] if package.wheels else package.sdist
    assert dist is not None
    assert dist.filename == filename
    assert pylock.to_dict() == data


def test_missing_sdist_filename() -> None:
    with pytest.raises(PylockValidationError) as exc_info:
        _ = PackageSdist(hashes={}).filename
    assert str(exc_info.value) == "Cannot determine sdist filename"


def test_missing_wheel_filename() -> None:
    with pytest.raises(PylockValidationError) as exc_info:
        _ = PackageWheel(hashes={}).filename
    assert str(exc_info.value) == "Cannot determine wheel filename"


def test_pylock_invalid_wheel_filename() -> None:
    data = {
        "lock-version": "1.0",
        "created-by": "pip",
        "packages": [
            {
                "name": "example",
                "wheels": [
                    {
                        "url": "http://example.com/example-1.0.whl",
                        "hashes": {"sha256": "f" * 40},
                    }
                ],
            }
        ],
    }
    with pytest.raises(PylockValidationError) as exc_info:
        Pylock.from_dict(data)
    assert str(exc_info.value) == (
        "Invalid wheel filename 'example-1.0.whl' in 'packages[0].wheels[0]'"
    )


def test_pylock_inconsistent_wheel_name() -> None:
    data = {
        "lock-version": "1.0",
        "created-by": "pip",
        "packages": [
            {
                "name": "foo",
                "wheels": [
                    {
                        "url": "http://example.com/bar-1.0-py3-none-any.whl",
                        "hashes": {"sha256": "f" * 40},
                    }
                ],
            }
        ],
    }
    with pytest.raises(PylockValidationError) as exc_info:
        Pylock.from_dict(data)
    assert str(exc_info.value) == (
        "Name in 'bar-1.0-py3-none-any.whl' is not consistent "
        "with package name 'foo' in 'packages[0].wheels[0]'"
    )


def test_pylock_inconsistent_wheel_version() -> None:
    data = {
        "lock-version": "1.0",
        "created-by": "pip",
        "packages": [
            {
                "name": "bar",
                "version": "2.0",
                "wheels": [
                    {
                        "url": "http://example.com/bar-1.0-py3-none-any.whl",
                        "hashes": {"sha256": "f" * 40},
                    }
                ],
            }
        ],
    }
    with pytest.raises(PylockValidationError) as exc_info:
        Pylock.from_dict(data)
    assert str(exc_info.value) == (
        "Version in 'bar-1.0-py3-none-any.whl' is not consistent "
        "with package version '2.0' in 'packages[0].wheels[0]'"
    )


def test_pylock_invalid_sdist_filename() -> None:
    data = {
        "lock-version": "1.0",
        "created-by": "pip",
        "packages": [
            {
                "name": "example",
                "sdist": {
                    "path": "./example.tar.gz",
                    "hashes": {"sha256": "f" * 40},
                },
            },
        ],
    }
    with pytest.raises(PylockValidationError) as exc_info:
        Pylock.from_dict(data)
    assert str(exc_info.value) == (
        "Invalid sdist filename 'example.tar.gz' in 'packages[0].sdist'"
    )


def test_pylock_inconsistent_sdist_name() -> None:
    data = {
        "lock-version": "1.0",
        "created-by": "pip",
        "packages": [
            {
                "name": "foo",
                "sdist": {
                    "path": "./bar-1.0.tar.gz",
                    "hashes": {"sha256": "f" * 40},
                },
            },
        ],
    }
    with pytest.raises(PylockValidationError) as exc_info:
        Pylock.from_dict(data)
    assert str(exc_info.value) == (
        "Name in 'bar-1.0.tar.gz' is not consistent "
        "with package name 'foo' in 'packages[0].sdist'"
    )


def test_pylock_inconsistent_sdist_version() -> None:
    data = {
        "lock-version": "1.0",
        "created-by": "pip",
        "packages": [
            {
                "name": "bar",
                "version": "2.0",
                "sdist": {
                    "path": "./bar-1.0.tar.gz",
                    "hashes": {"sha256": "f" * 40},
                },
            },
        ],
    }
    with pytest.raises(PylockValidationError) as exc_info:
        Pylock.from_dict(data)
    assert str(exc_info.value) == (
        "Version in 'bar-1.0.tar.gz' is not consistent "
        "with package version '2.0' in 'packages[0].sdist'"
    )


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
                    "upload-time": datetime.datetime(
                        2023, 10, 1, 0, 0, tzinfo=datetime.timezone.utc
                    ),
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
    ("hashes", "expected_error"),
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


def test_validate_attestation_identity_missing_kind() -> None:
    data = {
        "lock-version": "1.0",
        "created-by": "pip",
        "packages": [
            {
                "name": "example",
                "version": "1.0",
                "directory": {
                    "path": ".",
                },
                "attestation-identities": [
                    {
                        # missing "kind" field
                        "value": "some-value",
                    }
                ],
            }
        ],
    }
    with pytest.raises(PylockValidationError) as exc_info:
        Pylock.from_dict(data)
    assert str(exc_info.value) == (
        "Missing required value in 'packages[0].attestation-identities[0].kind'"
    )


def test_validate_attestation_identity_invalid_kind() -> None:
    data = {
        "lock-version": "1.0",
        "created-by": "pip",
        "packages": [
            {
                "name": "example",
                "version": "1.0",
                "directory": {
                    "path": ".",
                },
                "attestation-identities": [
                    {
                        "kind": 123,
                        "value": "some-value",
                    }
                ],
            }
        ],
    }
    with pytest.raises(PylockValidationError) as exc_info:
        Pylock.from_dict(data)
    assert str(exc_info.value) == (
        "Unexpected type int (expected str) "
        "in 'packages[0].attestation-identities[0].kind'"
    )


def _pickle_example() -> Pylock:
    hashes = {"sha256": "f" * 40}
    return Pylock.from_dict(
        {
            "lock-version": "1.0",
            "created-by": "pip",
            "environments": ["os_name == 'posix'"],
            "requires-python": ">=3.10",
            "packages": [
                {
                    "name": "a",
                    "version": "1.0",
                    "sdist": {"url": "https://e.com/a-1.0.tar.gz", "hashes": hashes},
                    "wheels": [
                        {
                            "url": "https://e.com/a-1.0-py3-none-any.whl",
                            "hashes": hashes,
                        }
                    ],
                },
                {
                    "name": "b",
                    "vcs": {
                        "type": "git",
                        "url": "https://g.c/b.git",
                        "commit-id": "a" * 40,
                    },
                },
                {"name": "c", "directory": {"path": "c", "editable": True}},
                {
                    "name": "d",
                    "archive": {"url": "https://e.com/d.zip", "hashes": hashes},
                },
            ],
            "tool": {"x": {"y": 1}},
        }
    )


def test_pickle_roundtrip() -> None:
    pylock = _pickle_example()
    assert pickle.loads(pickle.dumps(pylock)) == pylock
    assert copy.deepcopy(pylock) == pylock


def test_pickle_old_dict_state_loads() -> None:
    pylock = _pickle_example()
    # Dataclass equality also checks the type of each nested object.
    assert pickle.loads(pickle.dumps(_dict_state(pylock))) == pylock


# Generated with packaging==26.0, Python 3.13, pickle protocol 2.
_PICKLE_26_0 = (
    b"\x80\x02cpackaging.pylock\nPylock\nq\x00)\x81q\x01}q\x02(X\x0c\x00\x00"
    b"\x00lock_versionq\x03cpackaging.version\nVersion\nq\x04)\x81q\x05N}q"
    b"\x06(X\x04\x00\x00\x00_devq\x07NX\x06\x00\x00\x00_epochq\x08K\x00X\n"
    b"\x00\x00\x00_key_cacheq\x09(K\x00K\x01\x85q\ncpackaging._structures\nI"
    b"nfinityType\nq\x0b)\x81q\x0ccpackaging._structures\nNegativeInfinityTy"
    b"pe\nq\x0d)\x81q\x0eh\x0ch\x0etq\x0fX\x06\x00\x00\x00_localq\x10NX\x05"
    b"\x00\x00\x00_postq\x11NX\x04\x00\x00\x00_preq\x12NX\x08\x00\x00\x00_re"
    b"leaseq\x13K\x01K\x00\x86q\x14u\x86q\x15bX\x0c\x00\x00\x00environmentsq"
    b"\x16NX\x0f\x00\x00\x00requires_pythonq\x17cpackaging.specifiers\nSpeci"
    b"fierSet\nq\x18)\x81q\x19N}q\x1a(X\x0c\x00\x00\x00_prereleasesq\x1bNX"
    b"\x06\x00\x00\x00_specsq\x1cc__builtin__\nfrozenset\nq\x1d]q\x1ecpackag"
    b"ing.specifiers\nSpecifier\nq\x1f)\x81q N}q!(h\x1bNX\x05\x00\x00\x00_sp"
    b'ecq"X\x02\x00\x00\x00>=q#X\x04\x00\x00\x003.10q$\x86q%X\x0d\x00\x00'
    b"\x00_spec_versionq&h$h\x04)\x81q'N}q((h\x07Nh\x08K\x00h\x09Nh\x10Nh"
    b"\x11Nh\x12Nh\x13K\x03K\n\x86q)u\x86q*b\x86q+u\x86q,ba\x85q-Rq.u\x86q/b"
    b"X\x06\x00\x00\x00extrasq0NX\x11\x00\x00\x00dependency_groupsq1NX\x0e"
    b"\x00\x00\x00default_groupsq2NX\n\x00\x00\x00created_byq3X\x03\x00\x00"
    b"\x00pipq4X\x08\x00\x00\x00packagesq5]q6(cpackaging.pylock\nPackage\nq7"
    b")\x81q8}q9(X\x04\x00\x00\x00nameq:X\x01\x00\x00\x00aq;X\x07\x00\x00"
    b"\x00versionq<h\x04)\x81q=N}q>(h\x07Nh\x08K\x00h\x09Nh\x10Nh\x11Nh\x12N"
    b"h\x13K\x01K\x00\x86q?u\x86q@bX\x06\x00\x00\x00markerqAcpackaging.marke"
    b"rs\nMarker\nqB)\x81qC}qDX\x08\x00\x00\x00_markersqE]qFcpackaging._pars"
    b"er\nVariable\nqG)\x81qHN}qIX\x05\x00\x00\x00valueqJX\x07\x00\x00\x00os"
    b"_nameqKs\x86qLbcpackaging._parser\nOp\nqM)\x81qNN}qOhJX\x02\x00\x00"
    b"\x00==qPs\x86qQbcpackaging._parser\nValue\nqR)\x81qSN}qThJX\x05\x00"
    b"\x00\x00posixqUs\x86qVb\x87qWasbh\x17NX\x0c\x00\x00\x00dependenciesqXN"
    b"X\x03\x00\x00\x00vcsqYNX\x09\x00\x00\x00directoryqZNX\x07\x00\x00\x00a"
    b"rchiveq[NX\x05\x00\x00\x00indexq\\NX\x05\x00\x00\x00sdistq]NX\x06\x00"
    b"\x00\x00wheelsq^]q_cpackaging.pylock\nPackageWheel\nq`)\x81qa}qb(h:NX"
    b"\x0b\x00\x00\x00upload_timeqcNX\x03\x00\x00\x00urlqdX$\x00\x00\x00http"
    b"s://e.com/a-1.0-py3-none-any.whlqeX\x04\x00\x00\x00pathqfNX\x04\x00"
    b"\x00\x00sizeqgNX\x06\x00\x00\x00hashesqh}qiX\x06\x00\x00\x00sha256qjX"
    b"\x08\x00\x00\x00ffffffffqksubaX\x16\x00\x00\x00attestation_identitiesq"
    b"lNX\x04\x00\x00\x00toolqmNubh7)\x81qn}qo(h:X\x01\x00\x00\x00bqph<NhANh"
    b"\x17NhXNhYcpackaging.pylock\nPackageVcs\nqq)\x81qr}qs(X\x04\x00\x00"
    b"\x00typeqtX\x03\x00\x00\x00gitquhdX\x11\x00\x00\x00https://g.c/b.gitqv"
    b"hfNX\x12\x00\x00\x00requested_revisionqwNX\x09\x00\x00\x00commit_idqxX"
    b"\x08\x00\x00\x00aaaaaaaaqyX\x0c\x00\x00\x00subdirectoryqzNubhZNh[Nh\\N"
    b"h]Nh^NhlNhmNubehmNub."
)

# Generated with packaging==26.1, Python 3.13, pickle protocol 2.
_PICKLE_26_1 = (
    b"\x80\x02cpackaging.pylock\nPylock\nq\x00)\x81q\x01}q\x02(X\x0c\x00\x00"
    b"\x00lock_versionq\x03cpackaging.version\nVersion\nq\x04)\x81q\x05N}q"
    b"\x06(X\x04\x00\x00\x00_devq\x07NX\x06\x00\x00\x00_epochq\x08K\x00X\x0b"
    b"\x00\x00\x00_hash_cacheq\x09NX\n\x00\x00\x00_key_cacheq\nK\x00K\x01"
    b"\x85q\x0b(K\x03K\x00K\x00K\x00K\x01K\x00tq\x0c\x87q\x0dX\x06\x00\x00"
    b"\x00_localq\x0eNX\x05\x00\x00\x00_postq\x0fNX\x04\x00\x00\x00_preq\x10"
    b"NX\x08\x00\x00\x00_releaseq\x11K\x01K\x00\x86q\x12u\x86q\x13bX\x0c\x00"
    b"\x00\x00environmentsq\x14NX\x0f\x00\x00\x00requires_pythonq\x15cpackag"
    b"ing.specifiers\nSpecifierSet\nq\x16)\x81q\x17N}q\x18(X\x0e\x00\x00\x00"
    b"_canonicalizedq\x19\x88X\x0e\x00\x00\x00_has_arbitraryq\x1a\x89X\x11"
    b"\x00\x00\x00_is_unsatisfiableq\x1bNX\x0c\x00\x00\x00_prereleasesq\x1cN"
    b"X\x0d\x00\x00\x00_resolved_opsq\x1dNX\x06\x00\x00\x00_specsq\x1ecpacka"
    b"ging.specifiers\nSpecifier\nq\x1f)\x81q N}q!(h\x1cNX\x07\x00\x00\x00_r"
    b'angesq"NX\x05\x00\x00\x00_specq#X\x02\x00\x00\x00>=q$X\x04\x00\x00'
    b"\x003.10q%\x86q&X\x0d\x00\x00\x00_spec_versionq'NX\x0f\x00\x00\x00_wil"
    b"dcard_splitq(Nu\x86q)b\x85q*u\x86q+bX\x06\x00\x00\x00extrasq,NX\x11"
    b"\x00\x00\x00dependency_groupsq-NX\x0e\x00\x00\x00default_groupsq.NX\n"
    b"\x00\x00\x00created_byq/X\x03\x00\x00\x00pipq0X\x08\x00\x00\x00package"
    b"sq1]q2(cpackaging.pylock\nPackage\nq3)\x81q4}q5(X\x04\x00\x00\x00nameq"
    b"6X\x01\x00\x00\x00aq7X\x07\x00\x00\x00versionq8h\x04)\x81q9N}q:(h\x07N"
    b"h\x08K\x00h\x09Nh\nK\x00K\x01\x85q;h\x0c\x87q<h\x0eNh\x0fNh\x10Nh\x11K"
    b"\x01K\x00\x86q=u\x86q>bX\x06\x00\x00\x00markerq?cpackaging.markers\nMa"
    b"rker\nq@)\x81qAN}qBX\x08\x00\x00\x00_markersqC]qDcpackaging._parser\nV"
    b"ariable\nqE)\x81qFN}qGX\x05\x00\x00\x00valueqHX\x07\x00\x00\x00os_name"
    b"qIs\x86qJbcpackaging._parser\nOp\nqK)\x81qLN}qMhHX\x02\x00\x00\x00==qN"
    b"s\x86qObcpackaging._parser\nValue\nqP)\x81qQN}qRhHX\x05\x00\x00\x00pos"
    b"ixqSs\x86qTb\x87qUas\x86qVbh\x15NX\x0c\x00\x00\x00dependenciesqWNX\x03"
    b"\x00\x00\x00vcsqXNX\x09\x00\x00\x00directoryqYNX\x07\x00\x00\x00archiv"
    b"eqZNX\x05\x00\x00\x00indexq[NX\x05\x00\x00\x00sdistq\\NX\x06\x00\x00"
    b"\x00wheelsq]]q^cpackaging.pylock\nPackageWheel\nq_)\x81q`}qa(h6NX\x0b"
    b"\x00\x00\x00upload_timeqbNX\x03\x00\x00\x00urlqcX$\x00\x00\x00https://"
    b"e.com/a-1.0-py3-none-any.whlqdX\x04\x00\x00\x00pathqeNX\x04\x00\x00"
    b"\x00sizeqfNX\x06\x00\x00\x00hashesqg}qhX\x06\x00\x00\x00sha256qiX\x08"
    b"\x00\x00\x00ffffffffqjsubaX\x16\x00\x00\x00attestation_identitiesqkNX"
    b"\x04\x00\x00\x00toolqlNubh3)\x81qm}qn(h6X\x01\x00\x00\x00bqoh8Nh?Nh"
    b"\x15NhWNhXcpackaging.pylock\nPackageVcs\nqp)\x81qq}qr(X\x04\x00\x00"
    b"\x00typeqsX\x03\x00\x00\x00gitqthcX\x11\x00\x00\x00https://g.c/b.gitqu"
    b"heNX\x12\x00\x00\x00requested_revisionqvNX\x09\x00\x00\x00commit_idqwX"
    b"\x08\x00\x00\x00aaaaaaaaqxX\x0c\x00\x00\x00subdirectoryqyNubhYNhZNh[Nh"
    b"\\Nh]NhkNhlNubehlNub."
)

# Generated with packaging==26.3, Python 3.13, pickle protocol 2.
_PICKLE_26_3 = (
    b"\x80\x02cpackaging.pylock\nPylock\nq\x00)\x81q\x01}q\x02(X\x0c\x00\x00"
    b"\x00lock_versionq\x03cpackaging.version\nVersion\nq\x04)\x81q\x05(K"
    b"\x00K\x01K\x00\x86q\x06NNNNtq\x07bX\x0c\x00\x00\x00environmentsq\x08NX"
    b"\x0f\x00\x00\x00requires_pythonq\x09cpackaging.specifiers\nSpecifierSe"
    b"t\nq\n)\x81q\x0bcpackaging.specifiers\nSpecifier\nq\x0c)\x81q\x0dX\x02"
    b"\x00\x00\x00>=q\x0eX\x04\x00\x00\x003.10q\x0f\x86q\x10N\x86q\x11b\x85q"
    b"\x12N\x86q\x13bX\x06\x00\x00\x00extrasq\x14NX\x11\x00\x00\x00dependenc"
    b"y_groupsq\x15NX\x0e\x00\x00\x00default_groupsq\x16NX\n\x00\x00\x00crea"
    b"ted_byq\x17X\x03\x00\x00\x00pipq\x18X\x08\x00\x00\x00packagesq\x19]q"
    b"\x1a(cpackaging.pylock\nPackage\nq\x1b)\x81q\x1c}q\x1d(X\x04\x00\x00"
    b"\x00nameq\x1eX\x01\x00\x00\x00aq\x1fX\x07\x00\x00\x00versionq h\x04)"
    b'\x81q!(K\x00K\x01K\x00\x86q"NNNNtq#bX\x06\x00\x00\x00markerq$cpackagi'
    b'ng.markers\nMarker\nq%)\x81q&X\x12\x00\x00\x00os_name == "posix"q\'bh'
    b"\x09NX\x0c\x00\x00\x00dependenciesq(NX\x03\x00\x00\x00vcsq)NX\x09\x00"
    b"\x00\x00directoryq*NX\x07\x00\x00\x00archiveq+NX\x05\x00\x00\x00indexq"
    b",NX\x05\x00\x00\x00sdistq-NX\x06\x00\x00\x00wheelsq.]q/cpackaging.pylo"
    b"ck\nPackageWheel\nq0)\x81q1}q2(h\x1eNX\x0b\x00\x00\x00upload_timeq3NX"
    b"\x03\x00\x00\x00urlq4X$\x00\x00\x00https://e.com/a-1.0-py3-none-any.wh"
    b"lq5X\x04\x00\x00\x00pathq6NX\x04\x00\x00\x00sizeq7NX\x06\x00\x00\x00ha"
    b"shesq8}q9X\x06\x00\x00\x00sha256q:X\x08\x00\x00\x00ffffffffq;subaX\x16"
    b"\x00\x00\x00attestation_identitiesq<NX\x04\x00\x00\x00toolq=Nubh\x1b)"
    b"\x81q>}q?(h\x1eX\x01\x00\x00\x00bq@h Nh$Nh\x09Nh(Nh)cpackaging.pylock"
    b"\nPackageVcs\nqA)\x81qB}qC(X\x04\x00\x00\x00typeqDX\x03\x00\x00\x00git"
    b"qEh4X\x11\x00\x00\x00https://g.c/b.gitqFh6NX\x12\x00\x00\x00requested_"
    b"revisionqGNX\x09\x00\x00\x00commit_idqHX\x08\x00\x00\x00aaaaaaaaqIX"
    b"\x0c\x00\x00\x00subdirectoryqJNubh*Nh+Nh,Nh-Nh.Nh<Nh=Nubeh=Nub."
)

# Generated with packaging==26.4.dev0, Python 3.13, pickle protocol 2.
_PICKLE_26_4_DEV = (
    b"\x80\x02cpackaging.pylock\nPylock\nq\x00)\x81q\x01]q\x02(cpackaging.ve"
    b"rsion\nVersion\nq\x03)\x81q\x04(K\x00K\x01K\x00\x86q\x05NNNNtq\x06bNcp"
    b"ackaging.specifiers\nSpecifierSet\nq\x07)\x81q\x08cpackaging.specifier"
    b"s\nSpecifier\nq\x09)\x81q\nX\x02\x00\x00\x00>=q\x0bX\x04\x00\x00\x003."
    b"10q\x0c\x86q\x0dN\x86q\x0eb\x85q\x0fN\x86q\x10bNNNX\x03\x00\x00\x00pip"
    b"q\x11]q\x12(cpackaging.pylock\nPackage\nq\x13)\x81q\x14]q\x15(X\x01"
    b"\x00\x00\x00aq\x16h\x03)\x81q\x17(K\x00K\x01K\x00\x86q\x18NNNNtq\x19bc"
    b"packaging.markers\nMarker\nq\x1a)\x81q\x1bX\x12\x00\x00\x00os_name == "
    b'"posix"q\x1cbNNNNNNN]q\x1dcpackaging.pylock\nPackageWheel\nq\x1e)'
    b"\x81q\x1f]q (NNX$\x00\x00\x00https://e.com/a-1.0-py3-none-any.whlq!NN}"
    b'q"X\x06\x00\x00\x00sha256q#X\x08\x00\x00\x00ffffffffq$sebaNNebh\x13)'
    b"\x81q%]q&(X\x01\x00\x00\x00bq'NNNNcpackaging.pylock\nPackageVcs\nq()"
    b"\x81q)]q*(X\x03\x00\x00\x00gitq+X\x11\x00\x00\x00https://g.c/b.gitq,NN"
    b"X\x08\x00\x00\x00aaaaaaaaq-NebNNNNNNNebeNeb."
)


@pytest.mark.parametrize(
    "data",
    [_PICKLE_26_0, _PICKLE_26_1, _PICKLE_26_3, _PICKLE_26_4_DEV],
    ids=["26.0", "26.1", "26.3", "26.4.dev0"],
)
def test_pickle_from_older_version_loads(data: bytes) -> None:
    expected = Pylock.from_dict(
        {
            "lock-version": "1.0",
            "created-by": "pip",
            "requires-python": ">=3.10",
            "packages": [
                {
                    "name": "a",
                    "version": "1.0",
                    "marker": "os_name == 'posix'",
                    "wheels": [
                        {
                            "url": "https://e.com/a-1.0-py3-none-any.whl",
                            "hashes": {"sha256": "f" * 8},
                        }
                    ],
                },
                {
                    "name": "b",
                    "vcs": {
                        "type": "git",
                        "url": "https://g.c/b.git",
                        "commit-id": "a" * 8,
                    },
                },
            ],
        }
    )
    assert pickle.loads(data) == expected
