from __future__ import annotations

import dataclasses
import sys
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest

from packaging.markers import Marker
from packaging.pylock import (
    Package,
    PackageArchive,
    PackageDirectory,
    PackageSdist,
    PackageVcs,
    PackageWheel,
    Pylock,
    PylockSelectError,
)
from packaging.specifiers import SpecifierSet
from packaging.tags import Tag
from packaging.version import Version

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

if TYPE_CHECKING:
    from packaging.markers import Environment
    from packaging.utils import NormalizedName


@dataclasses.dataclass
class Platform:
    tags: list[Tag]
    environment: Environment


_py312_linux = Platform(
    tags=[
        Tag("cp312", "cp312", "manylinux_2_17_x86_64"),
        Tag("py3", "none", "any"),
    ],
    environment={
        "implementation_name": "cpython",
        "implementation_version": "3.12.12",
        "os_name": "posix",
        "platform_machine": "x86_64",
        "platform_release": "6.8.0-100-generic",
        "platform_system": "Linux",
        "platform_version": "#100-Ubuntu SMP PREEMPT_DYNAMIC",
        "python_full_version": "3.12.12",
        "platform_python_implementation": "CPython",
        "python_version": "3.12",
        "sys_platform": "linux",
    },
)


def test_smoke_test() -> None:
    pylock_path = Path(__file__).parent / "pylock" / "pylock.spec-example.toml"
    lock = Pylock.from_dict(tomllib.loads(pylock_path.read_text()))
    for package, dist in lock.select(
        tags=_py312_linux.tags,
        environment=_py312_linux.environment,
    ):
        assert isinstance(package, Package)
        assert isinstance(dist, PackageWheel)


def test_lock_no_matching_env() -> None:
    pylock = Pylock(
        lock_version=Version("1.0"),
        created_by="some_tool",
        environments=[Marker('python_version == "3.14"')],
        packages=[],
    )
    pylock.validate()
    with pytest.raises(
        PylockSelectError,
        match=(
            "Provided environment does not satisfy any of the "
            "environments specified in the lock file"
        ),
    ):
        list(
            pylock.select(
                tags=_py312_linux.tags,
                environment=_py312_linux.environment,
            )
        )


def test_lock_require_python_mismatch() -> None:
    pylock = Pylock(
        lock_version=Version("1.0"),
        created_by="some_tool",
        requires_python=SpecifierSet("==3.14.*"),
        packages=[],
    )
    pylock.validate()
    with pytest.raises(
        PylockSelectError,
        match="Provided environment does not satisfy the Python version requirement",
    ):
        list(
            pylock.select(
                tags=_py312_linux.tags,
                environment=_py312_linux.environment,
            )
        )


def test_package_require_python_mismatch() -> None:
    pylock = Pylock(
        lock_version=Version("1.0"),
        created_by="some_tool",
        packages=[
            Package(
                name=cast("NormalizedName", "foo"),
                version=Version("1.0"),
                requires_python=SpecifierSet("==3.14.*"),
                directory=PackageDirectory(path="."),
            ),
        ],
    )
    pylock.validate()
    with pytest.raises(
        PylockSelectError,
        match=(
            r"Provided environment does not satisfy the Python version requirement "
            r".* for package 'foo'"
        ),
    ):
        list(
            pylock.select(
                tags=_py312_linux.tags,
                environment=_py312_linux.environment,
            )
        )


def test_package_select_by_marker() -> None:
    pylock = Pylock(
        lock_version=Version("1.0"),
        created_by="some_tool",
        packages=[
            Package(
                name=cast("NormalizedName", "tomli"),
                marker=Marker('python_version < "3.11"'),
                version=Version("1.0"),
                archive=PackageArchive(
                    path="tomli-1.0.tar.gz", hashes={"sha256": "abc123"}
                ),
            ),
            Package(
                name=cast("NormalizedName", "foo"),
                marker=Marker('python_version >= "3.11"'),
                version=Version("1.0"),
                archive=PackageArchive(
                    path="foo-1.0.tar.gz", hashes={"sha256": "abc123"}
                ),
            ),
        ],
    )
    pylock.validate()
    selected = list(
        pylock.select(
            tags=_py312_linux.tags,
            environment=_py312_linux.environment,
        )
    )
    assert len(selected) == 1
    assert selected[0][0].name == "foo"


def test_duplicate_packages() -> None:
    pylock = Pylock(
        lock_version=Version("1.0"),
        created_by="some_tool",
        packages=[
            Package(
                name=cast("NormalizedName", "foo"),
                version=Version("1.0"),
                archive=PackageArchive(
                    path="tomli-1.0.tar.gz", hashes={"sha256": "abc123"}
                ),
            ),
            Package(
                name=cast("NormalizedName", "foo"),
                version=Version("2.0"),
                archive=PackageArchive(
                    path="foo-1.0.tar.gz", hashes={"sha256": "abc123"}
                ),
            ),
        ],
    )
    pylock.validate()
    with pytest.raises(
        PylockSelectError,
        match=(
            r"Multiple packages with the name 'foo' are selected "
            r"at packages\[1\] and packages\[0\]"
        ),
    ):
        list(
            pylock.select(
                tags=_py312_linux.tags,
                environment=_py312_linux.environment,
            )
        )


def test_yield_all_types() -> None:
    pylock = Pylock(
        lock_version=Version("1.0"),
        created_by="some_tool",
        packages=[
            Package(
                name=cast("NormalizedName", "foo-archive"),
                archive=PackageArchive(
                    path="tomli-1.0.tar.gz", hashes={"sha256": "abc123"}
                ),
            ),
            Package(
                name=cast("NormalizedName", "foo-directory"),
                directory=PackageDirectory(path="./foo-directory"),
            ),
            Package(
                name=cast("NormalizedName", "foo-vcs"),
                vcs=PackageVcs(
                    type="git", url="https://example.com/foo.git", commit_id="fa123"
                ),
            ),
            Package(
                name=cast("NormalizedName", "foo-sdist"),
                sdist=PackageSdist(path="foo-1.0.tar.gz", hashes={"sha256": "abc123"}),
            ),
            Package(
                name=cast("NormalizedName", "foo-wheel"),
                wheels=[
                    PackageWheel(
                        name="foo-1.0-py3-none-any.whl",
                        path="./foo-1.0-py3-none-any.whl",
                        hashes={"sha256": "abc123"},
                    )
                ],
            ),
        ],
    )
    pylock.validate()
    selected = list(pylock.select())
    assert len(selected) == 5


def test_sdist_fallback() -> None:
    pylock = Pylock(
        lock_version=Version("1.0"),
        created_by="some_tool",
        packages=[
            Package(
                name=cast("NormalizedName", "foo"),
                sdist=PackageSdist(
                    path="foo-1.0.tar.gz",
                    hashes={"sha256": "abc123"},
                ),
                wheels=[
                    PackageWheel(
                        name="foo-1.0-py5-none-any.whl",
                        path="./foo-1.0-py5-none-any.whl",
                        hashes={"sha256": "abc123"},
                    )
                ],
            ),
        ],
    )
    selected = list(pylock.select())
    assert len(selected) == 1
    assert isinstance(selected[0][1], PackageSdist)


def test_missing_sdist_fallback() -> None:
    pylock = Pylock(
        lock_version=Version("1.0"),
        created_by="some_tool",
        packages=[
            Package(
                name=cast("NormalizedName", "foo"),
                wheels=[
                    PackageWheel(
                        name="foo-1.0-py5-none-any.whl",
                        path="./foo-1.0-py5-none-any.whl",
                        hashes={"sha256": "abc123"},
                    )
                ],
            ),
        ],
    )
    pylock.validate()
    with pytest.raises(
        PylockSelectError, match=r"No wheel found matching .* and no sdist available"
    ):
        list(pylock.select())


@pytest.mark.parametrize(
    ("extras", "dependency_groups", "expected"),
    [
        (None, None, ["foo", "foo-dev"]),  # select default_groups
        (None, ["dev"], ["foo", "foo-dev"]),  # same as default_groups
        (None, [], ["foo"]),  # select no groups
        (None, ["docs"], ["foo", "foo-docs"]),
        (None, ["dev", "docs"], ["foo", "foo-dev", "foo-docs"]),
        ([], None, ["foo", "foo-dev"]),
        (["feat1"], None, ["foo", "foo-dev", "foo-feat1"]),
        (["feat2"], None, ["foo", "foo-dev", "foo-feat2"]),
        (["feat1", "feat2"], None, ["foo", "foo-dev", "foo-feat1", "foo-feat2"]),
        (["feat1", "feat2"], ["docs"], ["foo", "foo-docs", "foo-feat1", "foo-feat2"]),
    ],
)
def test_extras_and_groups(
    extras: list[str] | None,
    dependency_groups: list[str] | None,
    expected: list[str],
) -> None:
    pylock = Pylock(
        lock_version=Version("1.0"),
        created_by="some_tool",
        extras=[cast("NormalizedName", "feat1"), cast("NormalizedName", "feat2")],
        dependency_groups=["dev", "docs"],
        default_groups=["dev"],
        packages=[
            Package(
                name=cast("NormalizedName", "foo"),
                directory=PackageDirectory(path="./foo"),
            ),
            Package(
                name=cast("NormalizedName", "foo-dev"),
                directory=PackageDirectory(path="./foo-dev"),
                marker=Marker("'dev' in dependency_groups"),
            ),
            Package(
                name=cast("NormalizedName", "foo-docs"),
                directory=PackageDirectory(path="./foo-docs"),
                marker=Marker("'docs' in dependency_groups"),
            ),
            Package(
                name=cast("NormalizedName", "foo-feat1"),
                directory=PackageDirectory(path="./foo-feat1"),
                marker=Marker("'feat1' in extras"),
            ),
            Package(
                name=cast("NormalizedName", "foo-feat2"),
                directory=PackageDirectory(path="./foo-feat2"),
                marker=Marker("'feat2' in extras"),
            ),
        ],
    )
    pylock.validate()
    selected_names = [
        package.name
        for package, _ in pylock.select(
            extras=extras,
            dependency_groups=dependency_groups,
        )
    ]
    assert selected_names == expected
