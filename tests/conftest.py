from __future__ import annotations

import sysconfig


def pytest_report_header() -> str:
    lines = [f"sysconfig platform: {sysconfig.get_platform()}"]
    if sysconfig.get_config_var("Py_GIL_DISABLED"):
        lines.append("free-threaded Python build")
    return "\n".join(lines)
