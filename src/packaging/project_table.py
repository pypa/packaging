# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.

from __future__ import annotations

import sys
import typing
from typing import Any, Dict, List, Literal, TypedDict, Union

if sys.version_info < (3, 11):
    from typing_extensions import Required
else:
    from typing import Required


__all__ = [
    "BuildSystemTable",
    "ContactTable",
    "Dynamic",
    "IncludeGroupTable",
    "LicenseTable",
    "ProjectTable",
    "PyProjectTable",
    "ReadmeTable",
]


def __dir__() -> list[str]:
    return __all__


class ContactTable(TypedDict, total=False):
    name: str
    email: str


class LicenseTable(TypedDict, total=False):
    text: str
    file: str


ReadmeTable = TypedDict(
    "ReadmeTable", {"file": str, "text": str, "content-type": str}, total=False
)

Dynamic = Literal[
    "authors",
    "classifiers",
    "dependencies",
    "description",
    "dynamic",
    "entry-points",
    "gui-scripts",
    "import-names",
    "import-namespaces",
    "keywords",
    "license",
    "maintainers",
    "optional-dependencies",
    "readme",
    "requires-python",
    "scripts",
    "urls",
    "version",
]

ProjectTable = TypedDict(
    "ProjectTable",
    {
        "name": Required[str],
        "version": str,
        "description": str,
        "license": Union[LicenseTable, str],
        "license-files": List[str],
        "readme": Union[str, ReadmeTable],
        "requires-python": str,
        "dependencies": List[str],
        "optional-dependencies": Dict[str, List[str]],
        "entry-points": Dict[str, Dict[str, str]],
        "authors": List[ContactTable],
        "maintainers": List[ContactTable],
        "urls": Dict[str, str],
        "classifiers": List[str],
        "keywords": List[str],
        "scripts": Dict[str, str],
        "gui-scripts": Dict[str, str],
        "import-names": List[str],
        "import-namespaces": List[str],
        "dynamic": List[Dynamic],
    },
    total=False,
)

BuildSystemTable = TypedDict(
    "BuildSystemTable",
    {
        "build-backend": str,
        "requires": List[str],
        "backend-path": List[str],
    },
    total=False,
)

# total=False here because this could be
# extended in the future
IncludeGroupTable = TypedDict(
    "IncludeGroupTable",
    {"include-group": str},
    total=False,
)

PyProjectTable = TypedDict(
    "PyProjectTable",
    {
        "build-system": BuildSystemTable,
        "project": ProjectTable,
        "tool": Dict[str, Any],
        "dependency-groups": Dict[str, List[Union[str, IncludeGroupTable]]],
    },
    total=False,
)

# Tests for type checking
if typing.TYPE_CHECKING:
    PyProjectTable(
        {
            "build-system": BuildSystemTable(
                {"build-backend": "one", "requires": ["two"]}
            ),
            "project": ProjectTable(
                {
                    "name": "one",
                    "version": "0.1.0",
                }
            ),
            "tool": {"thing": object()},
            "dependency-groups": {
                "one": [
                    "one",
                    IncludeGroupTable({"include-group": "two"}),
                ]
            },
        }
    )
