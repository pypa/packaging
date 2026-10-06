# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.

# Helpers for the in-browser validator page. These run in Pyodide and
# return JSON strings for ``validator.js`` to render.

from __future__ import annotations

import json
import sys
from typing import Any

import packaging
from packaging.requirements import InvalidRequirement, Requirement
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

INFO = f"packaging {packaging.__version__}, Python {sys.version.split()[0]}"


def _result(ok: bool, rows: dict[str, Any]) -> str:
    return json.dumps({"ok": ok, "rows": [[k, str(v)] for k, v in rows.items()]})


def check_version(text: str) -> str:
    try:
        v = Version(text)
    except InvalidVersion as err:
        return _result(False, {"Error": err})
    return _result(
        True,
        {
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
        },
    )


def check_requirement(text: str) -> str:
    try:
        req = Requirement(text)
    except InvalidRequirement as err:
        return _result(False, {"Error": err})
    return _result(
        True,
        {
            "Normalized": req,
            "Name": req.name,
            "Extras": ", ".join(sorted(req.extras)) or None,
            "Specifier": req.specifier or None,
            "URL": req.url,
            "Marker": req.marker,
        },
    )


def check_specifier(text: str, version: str) -> str:
    try:
        spec = SpecifierSet(text)
    except InvalidSpecifier as err:
        return _result(False, {"Error": err})
    rows: dict[str, Any] = {"Normalized": spec}
    if version:
        try:
            v = Version(version)
        except InvalidVersion as err:
            return _result(False, {**rows, "Error": err})
        rows[f"Contains {v}"] = spec.contains(v)
    return _result(True, rows)
