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
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest

from packaging.markers import Environment, default_environment
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
        {"python_version": "3.14"},
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
    lock = _lock(">=3.99")
    with pytest.raises(PylockSelectError):
        list(lock.select(environment=default_environment()))
    assert _selected(
        lock, {**default_environment(), "python_full_version": "3.99.0"}
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
