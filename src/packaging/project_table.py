# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.

from __future__ import annotations

import sys
import typing
from typing import Any, Dict, List, Literal, TypedDict, Union

if sys.version_info < (3, 11):
    if typing.TYPE_CHECKING:
        from typing_extensions import Required
    else:
        try:
            from typing_extensions import Required
        except ModuleNotFoundError:
            V = typing.TypeVar("V")

            class Required:
                def __class_getitem__(cls, item: V) -> V:
                    return item
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
    "to_project_table",
]


def __dir__() -> list[str]:
    return __all__


class ContactTable(TypedDict, total=False):
    """
    Can have either name or email.
    """

    name: str
    email: str


class LicenseTable(TypedDict, total=False):
    """
    Can have either text or file. Legacy.
    """

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

T = typing.TypeVar("T")


def is_typed_dict(type_hint: object) -> bool:
    if sys.version_info >= (3, 10):
        return typing.is_typeddict(type_hint)
    return hasattr(type_hint, "__annotations__") and hasattr(type_hint, "__total__")


def _cast(type_hint: type[T], data: object, prefix: str) -> T:
    """
    Runtime cast for types.

    Just enough to cover the dicts above (not general or public).
    """

    # TypedDict
    if is_typed_dict(type_hint):
        if not isinstance(data, dict):
            msg = (
                f'"{prefix}" expected dict for {type_hint.__name__},'
                f" got {type(data).__name__}"
            )
            raise TypeError(msg)

        hints = typing.get_type_hints(type_hint)
        for key, typ in hints.items():
            if key in data:
                _cast(typ, data[key], prefix + f".{key}" if prefix else key)
            # Required keys could be enforced here on 3.11+ eventually

        return typing.cast("T", data)

    origin = typing.get_origin(type_hint)
    # Special case Required on 3.10
    if origin is Required:
        (type_hint,) = typing.get_args(type_hint)
        origin = typing.get_origin(type_hint)
    args = typing.get_args(type_hint)

    # Literal
    if origin is typing.Literal:
        if data not in args:
            arg_names = ", ".join(repr(a) for a in args)
            msg = f'"{prefix}" expected one of {arg_names}, got {data!r}'
            raise TypeError(msg)
        return typing.cast("T", data)

    # Any accepts everything, so no validation
    if type_hint is Any:
        return typing.cast("T", data)

    # List[T]
    if origin is list:
        if not isinstance(data, list):
            msg = f'"{prefix}" expected list, got {type(data).__name__}'
            raise TypeError(msg)
        item_type = args[0]
        return typing.cast(
            "T", [_cast(item_type, item, f"{prefix}[]") for item in data]
        )

    # Dict[str, T]
    if origin is dict:
        if not isinstance(data, dict):
            msg = f'"{prefix}" expected dict, got {type(data).__name__}'
            raise TypeError(msg)
        _, value_type = args
        return typing.cast(
            "T",
            {
                key: _cast(value_type, value, f"{prefix}.{key}")
                for key, value in data.items()
            },
        )
    # Union[T1, T2, ...]
    if origin is typing.Union:
        for arg in args:
            try:
                _cast(arg, data, prefix)
                return typing.cast("T", data)
            except TypeError:  # noqa: PERF203
                continue
        arg_names = " | ".join(a.__name__ for a in args)
        msg = f'"{prefix}" does not match any type in {arg_names}'
        raise TypeError(msg)

    # Base case (str, etc.)
    if isinstance(data, origin or type_hint):
        return typing.cast("T", data)

    msg = f'"{prefix}" expected {type_hint.__name__}, got {type(data).__name__}'
    raise TypeError(msg)


def to_project_table(data: dict[str, Any], /) -> PyProjectTable:
    """
    Convert a dict to a PyProjectTable, validating types at runtime.

    Note that only the types that are affected by a TypedDict are validated;
    extra keys are ignored.
    """
    # Handling Required here
    name = data.get("project", {"name": ""}).get("name")
    if name is None:
        msg = 'Key "project.name" is required if "project" is present'
        raise TypeError(msg)
    return _cast(PyProjectTable, data, "")
