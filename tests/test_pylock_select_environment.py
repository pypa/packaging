"""Regression tests: ``Pylock.select()`` must not raise a bare ``KeyError``
for a partial ``environment`` mapping.

``select()`` documents the contract for this parameter itself, two lines above
the read: ``dict(environment or {}, ...)  # Marker.evaluate will fill-up``.  So
``environment`` carries *overrides* merged over ``default_environment()``, which
is exactly what ``Marker.evaluate()`` does (``markers.py``: ``current_environment
|= environment``).

The ``requires-python`` read instead subscripted ``environment`` directly, so the
override semantics held for ``packages.marker`` but not here.  An empty mapping
is falsy and accidentally took the default branch; any other partial mapping
raised an unhandled ``KeyError`` out of a generator whose documented failure
mode is ``PylockSelectError``.

The second half of the file covers the two spellings of the interpreter.
``python_version`` (``major.minor``) and ``python_full_version``
(``major.minor.patch``) were read from different places, so overriding only
``python_version`` made the ``requires-python`` checks and the marker checks
describe different interpreters -- one the override, the other the host running
``select()``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest

from packaging.markers import Environment, Marker, default_environment
from packaging.pylock import Package, PackageDirectory, Pylock, PylockSelectError
from packaging.specifiers import SpecifierSet
from packaging.version import Version

if TYPE_CHECKING:
    from collections.abc import Mapping
    from collections.abc import Set as AbstractSet

    from packaging.utils import NormalizedName


def _lock(requires_python: str = ">=3.8") -> Pylock:
    pylock = Pylock(
        lock_version=Version("1.0"),
        created_by="some_tool",
        requires_python=SpecifierSet(requires_python),
        packages=[
            Package(
                name=cast("NormalizedName", "foo"),
                directory=PackageDirectory(path="./foo"),
            ),
        ],
    )
    pylock.validate()
    return pylock


def _selected(
    pylock: Pylock,
    environment: Environment | Mapping[str, str | AbstractSet[str]],
) -> list[str]:
    return [package.name for package, _ in pylock.select(environment=environment)]


@pytest.mark.parametrize(
    "environment",
    [
        {"sys_platform": "linux"},
        {"os_name": "posix"},
        {"implementation_name": "cpython"},
        {"platform_machine": "x86_64"},
    ],
)
def test_partial_environment_is_merged_over_defaults(
    environment: Environment | Mapping[str, str | AbstractSet[str]],
) -> None:
    """A partial override set selects as if it were merged, not subscripted."""
    assert _selected(_lock(), environment) == ["foo"]


def test_empty_environment_behaves_like_default() -> None:
    """Pre-existing behaviour: ``{}`` is falsy and took the default branch."""
    assert _selected(_lock(), {}) == ["foo"]


def test_full_environment_still_selects() -> None:
    assert _selected(_lock(), default_environment()) == ["foo"]


def test_override_of_python_full_version_is_honoured() -> None:
    """A real override is still respected instead of being silently defaulted."""
    lock = _lock(">=9.0")
    with pytest.raises(PylockSelectError):
        list(lock.select(environment=default_environment()))
    assert _selected(
        lock, {**default_environment(), "python_full_version": "9.0.1"}
    ) == ["foo"]


def test_unsatisfiable_requires_python_still_raises_select_error() -> None:
    """The documented failure mode is preserved, including on a partial env."""
    with pytest.raises(PylockSelectError):
        list(_lock(">=99.0").select(environment={"sys_platform": "linux"}))


def test_set_valued_python_full_version_is_refused() -> None:
    """A set-valued override is a caller error, reported as a select error."""
    lock = _lock(">=3.8")
    with pytest.raises(PylockSelectError, match="python_full_version"):
        list(lock.select(environment={"python_full_version": frozenset({"3.14"})}))


def test_python_version_override_is_honoured_by_requires_python() -> None:
    """``python_version`` alone must reach the ``requires-python`` check.

    The markers already saw the override (``Marker.evaluate`` merges it over
    the default), so reading ``python_full_version`` off the host here made the
    two checks describe different interpreters. ``python_version`` does not
    carry a patch level, so it is refused rather than guessed at.
    """
    with pytest.raises(PylockSelectError, match="python_full_version"):
        list(_lock(">=9.0").select(environment={"python_version": "9.9"}))


def test_python_version_override_reaches_the_marker_checks() -> None:
    """``requires-python`` and ``packages.marker`` must agree on the version."""
    lock = Pylock(
        lock_version=Version("1.0"),
        created_by="some_tool",
        requires_python=SpecifierSet(">=9.0"),
        packages=[
            Package(
                name=cast("NormalizedName", "foo"),
                marker=Marker("python_version >= '9.9'"),
                directory=PackageDirectory(path="./foo"),
            ),
        ],
    )
    lock.validate()
    # Both checks read the same override: the marker selects the package and
    # the lock's ``requires-python`` is satisfied by the same 9.9.
    assert _selected(lock, {"python_full_version": "9.9.1"}) == ["foo"]


def test_derived_python_version_matches_the_full_version() -> None:
    """The ``major.minor`` spelling follows ``python_full_version``."""
    lock = Pylock(
        lock_version=Version("1.0"),
        created_by="some_tool",
        packages=[
            Package(
                name=cast("NormalizedName", "foo"),
                marker=Marker("python_version == '9.9'"),
                directory=PackageDirectory(path="./foo"),
            ),
        ],
    )
    lock.validate()
    assert _selected(lock, {"python_full_version": "9.9.1"}) == ["foo"]
    # A different interpreter no longer matches the marker, so the package is
    # skipped rather than selected for the wrong version.
    assert _selected(lock, {"python_full_version": "9.8.0"}) == []


def test_set_valued_python_version_is_refused() -> None:
    """A set-valued ``python_version`` cannot pin an interpreter either."""
    with pytest.raises(PylockSelectError, match="python_version"):
        list(_lock().select(environment={"python_version": frozenset({"3.14"})}))


def test_agreeing_version_overrides_are_accepted() -> None:
    """The same interpreter written both ways is not a conflict."""
    assert _selected(
        _lock(), {"python_version": "3.8", "python_full_version": "3.8"}
    ) == ["foo"]
    assert _selected(_lock(">=3.8.2"), {"python_full_version": "3.8.2"}) == ["foo"]
    with pytest.raises(PylockSelectError):
        list(_lock(">=3.8.2").select(environment={"python_full_version": "3.8.1"}))


def test_environments_see_the_same_version_as_the_marker_checks() -> None:
    """``pylock.environments`` is evaluated against the resolved environment."""
    lock = Pylock(
        lock_version=Version("1.0"),
        created_by="some_tool",
        environments=[Marker("python_version >= '9.9'")],
        packages=[
            Package(
                name=cast("NormalizedName", "foo"),
                directory=PackageDirectory(path="./foo"),
            ),
        ],
    )
    lock.validate()
    assert _selected(lock, {"python_full_version": "9.9.1"}) == ["foo"]
    with pytest.raises(PylockSelectError):
        list(lock.select(environment={"python_full_version": "2.7.0"}))
