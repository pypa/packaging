# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.

# Helpers for the in-browser validator page. These run in Pyodide; ``run``
# returns a JSON string for ``validator.js`` to render.

from __future__ import annotations

import json
import sys
from typing import TYPE_CHECKING, Any

import packaging
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.version import InvalidVersion, Version

if TYPE_CHECKING:
    from collections.abc import Callable


def info() -> dict[str, Any]:
    return {
        "Info": f"packaging {packaging.__version__}, Python {sys.version.split()[0]}"
    }


def check_version(text: str) -> dict[str, Any]:
    v = Version(text)
    return {
        "Normalized": v,
        "Epoch": v.epoch,
        "Release": v.release,
        "Pre": v.pre,
        "Post": v.post,
        "Dev": v.dev,
        "Local": v.local,
        "Public": v.public,
        "Base version": v.base_version,
        "Is pre-release": v.is_prerelease,
        "Is post-release": v.is_postrelease,
        "Is dev release": v.is_devrelease,
    }


def check_requirement(text: str) -> dict[str, Any]:
    req = Requirement(text)
    return {
        "Normalized": req,
        "Name": req.name,
        "Extras": ", ".join(sorted(req.extras)) or None,
        "Specifier": req.specifier or None,
        "URL": req.url,
        "Marker": req.marker,
    }


def check_specifier(text: str, version: str) -> dict[str, Any]:
    spec = SpecifierSet(text)
    rows: dict[str, Any] = {"Normalized": spec}
    if version:
        try:
            v = Version(version)
        except InvalidVersion as err:
            rows["Error"] = err
        else:
            rows[f"Contains {v}"] = spec.contains(v)
    return rows


CHECKS: dict[str, Callable[..., dict[str, Any]]] = {
    "info": info,
    "check_version": check_version,
    "check_requirement": check_requirement,
    "check_specifier": check_specifier,
}


def run(name: str, *args: str) -> str:
    """Run a check and return ``{"ok", "rows"}`` as JSON.

    All ``Invalid*`` exceptions are ``ValueError`` subclasses.
    """
    try:
        rows = CHECKS[name](*args)
    except ValueError as err:
        rows = {"Error": err}
    return json.dumps(
        {"ok": "Error" not in rows, "rows": {k: str(v) for k, v in rows.items()}}
    )
