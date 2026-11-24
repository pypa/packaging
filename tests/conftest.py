from __future__ import annotations

import gc
import sysconfig
from typing import TYPE_CHECKING

from packaging.markers import _cached_default_environment

if TYPE_CHECKING:
    import pytest


# default_environment() is cached, so tests that patch platform/sys must run
# against a fresh cache and must not leak their patched values to later tests.
# Plain hooks are used instead of an autouse fixture because instantiating a
# fixture 62k times costs several percent of the suite's runtime.
def pytest_runtest_setup() -> None:
    _cached_default_environment.cache_clear()


def pytest_runtest_teardown() -> None:
    _cached_default_environment.cache_clear()


def pytest_collection() -> None:
    # Collection allocates millions of long-lived objects; skip GC passes until
    # the collect-and-freeze below.
    gc.disable()


def pytest_collection_finish(session: pytest.Session) -> None:
    # Freeze the collected-item tree and imported modules into GC's permanent
    # generation so per-test GC passes stop traversing them (~10% faster suite).
    gc.enable()
    gc.collect()
    # Hypothesis cannot inspect references held by frozen containers.
    property_run = any(item.get_closest_marker("property") for item in session.items)
    if hasattr(gc, "freeze") and not property_run:  # CPython-only; missing on PyPy
        gc.freeze()


def pytest_report_header() -> str:
    lines = [f"sysconfig platform: {sysconfig.get_platform()}"]
    if sysconfig.get_config_var("Py_GIL_DISABLED"):
        lines.append("free-threaded Python build")
    return "\n".join(lines)
