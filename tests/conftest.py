from __future__ import annotations

import sysconfig
import typing

import pytest

from packaging.markers import _cached_default_environment

if typing.TYPE_CHECKING:
    from collections.abc import Generator


@pytest.fixture(autouse=True)
def _clear_default_environment_cache() -> Generator[None, None, None]:
    # default_environment() is cached, so tests that patch platform/sys must run
    # against a fresh cache and must not leak their patched values to later tests.
    _cached_default_environment.cache_clear()
    yield
    _cached_default_environment.cache_clear()


def pytest_report_header() -> str:
    lines = [f"sysconfig platform: {sysconfig.get_platform()}"]
    if sysconfig.get_config_var("Py_GIL_DISABLED"):
        lines.append("free-threaded Python build")
    return "\n".join(lines)
