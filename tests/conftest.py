from __future__ import annotations

import gc
import sysconfig

from packaging.markers import _cached_default_environment


# default_environment() is cached, so tests that patch platform/sys must run
# against a fresh cache and must not leak their patched values to later tests.
# Plain hooks are used instead of an autouse fixture because instantiating a
# fixture 62k times costs several percent of the suite's runtime.
def pytest_runtest_setup() -> None:
    _cached_default_environment.cache_clear()


def pytest_runtest_teardown() -> None:
    _cached_default_environment.cache_clear()


def pytest_collection_finish() -> None:
    # Freeze the collected-item tree and imported modules into GC's permanent
    # generation so per-test GC passes stop traversing them (~10% faster suite).
    gc.collect()
    if hasattr(gc, "freeze"):  # CPython-only; missing on PyPy
        gc.freeze()


def pytest_report_header() -> str:
    lines = [f"sysconfig platform: {sysconfig.get_platform()}"]
    if sysconfig.get_config_var("Py_GIL_DISABLED"):
        lines.append("free-threaded Python build")
    return "\n".join(lines)
