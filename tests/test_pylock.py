from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from textwrap import dedent
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


# This is the PEP 751 example, with the following differences:
# - a minor modification to the 'environments' field to use double quotes
#   instead of single quotes, since that is what 'packaging' does when
#   serializing markers;
# - added an index field, which was not demonstrated in the PEP 751 example.

PEP751_EXAMPLE = dedent(
    """\
    lock-version = '1.0'
    environments = ["sys_platform == \\"win32\\"", "sys_platform == \\"linux\\""]
    requires-python = '==3.12'
    created-by = 'mousebender'

    [[packages]]
    name = 'attrs'
    version = '25.1.0'
    requires-python = '>=3.8'
    wheels = [
    {name = 'attrs-25.1.0-py3-none-any.whl', upload-time = 2025-01-25T11:30:10.164985+00:00, url = 'https://files.pythonhosted.org/packages/fc/30/d4986a882011f9df997a55e6becd864812ccfcd821d64aac8570ee39f719/attrs-25.1.0-py3-none-any.whl', size = 63152, hashes = {sha256 = 'c75a69e28a550a7e93789579c22aa26b0f5b83b75dc4e08fe092980051e1090a'}},
    ]
    [[packages.attestation-identities]]
    environment = 'release-pypi'
    kind = 'GitHub'
    repository = 'python-attrs/attrs'
    workflow = 'pypi-package.yml'

    [[packages]]
    name = 'cattrs'
    version = '24.1.2'
    requires-python = '>=3.8'
    dependencies = [
        {name = 'attrs'},
    ]
    index = 'https://pypi.org/simple'
    wheels = [
    {name = 'cattrs-24.1.2-py3-none-any.whl', upload-time = 2024-09-22T14:58:34.812643+00:00, url = 'https://files.pythonhosted.org/packages/c8/d5/867e75361fc45f6de75fe277dd085627a9db5ebb511a87f27dc1396b5351/cattrs-24.1.2-py3-none-any.whl', size = 66446, hashes = {sha256 = '67c7495b760168d931a10233f979b28dc04daf853b30752246f4f8471c6d68d0'}},
    ]

    [[packages]]
    name = 'numpy'
    version = '2.2.3'
    requires-python = '>=3.10'
    wheels = [
    {name = 'numpy-2.2.3-cp312-cp312-win_amd64.whl', upload-time = 2025-02-13T16:51:21.821880+00:00, url = 'https://files.pythonhosted.org/packages/42/6e/55580a538116d16ae7c9aa17d4edd56e83f42126cb1dfe7a684da7925d2c/numpy-2.2.3-cp312-cp312-win_amd64.whl', size = 12626357, hashes = {sha256 = '83807d445817326b4bcdaaaf8e8e9f1753da04341eceec705c001ff342002e5d'}},
    {name = 'numpy-2.2.3-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl', upload-time = 2025-02-13T16:50:00.079662+00:00, url = 'https://files.pythonhosted.org/packages/39/04/78d2e7402fb479d893953fb78fa7045f7deb635ec095b6b4f0260223091a/numpy-2.2.3-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl', size = 16116679, hashes = {sha256 = '3b787adbf04b0db1967798dba8da1af07e387908ed1553a0d6e74c084d1ceafe'}},
    ]

    [tool.mousebender]
    command = ['.', 'lock', '--platform', 'cpython3.12-windows-x64', '--platform', 'cpython3.12-manylinux2014-x64', 'cattrs', 'numpy']
    run-on = 2025-03-06T12:28:57.760769
    """  # noqa: E501
)


def test_toml_roundtrip() -> None:
    pylock_dict = tomllib.loads(PEP751_EXAMPLE)
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


def test_pylock_unsupported_version() -> None:
    data = {
        "lock-version": "2.0",
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
        PackageVcs(type="git", url=None, path=None, commit_id="f" * 40)
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
            "Hash values must be strings",
        ),
        (
            {},
            "At least one hash must be provided",
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
