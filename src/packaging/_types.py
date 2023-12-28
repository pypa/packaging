"""Types used internally.

This module defines types separately so that there is no runtime cost.
"""
from __future__ import annotations

from typing import Any, Callable, List, NewType, Sequence, Tuple, TypeVar, Union

from ._parser import Op, Value, Variable
from ._structures import InfinityType, NegativeInfinityType
from .version import Version

MarkerVar = Union[Variable, Value]
MarkerItem = Tuple[MarkerVar, Op, MarkerVar]
# MarkerAtom = Union[MarkerItem, List["MarkerAtom"]]
# MarkerList = List[Union["MarkerList", MarkerAtom, str]]
# mypy does not support recursive type definition
# https://github.com/python/mypy/issues/731
MarkerAtom = Any
MarkerList = List[Any]

UnparsedVersion = Union[Version, str]
UnparsedVersionVar = TypeVar("UnparsedVersionVar", bound=UnparsedVersion)
CallableOperator = Callable[[Version, str], bool]

PythonVersion = Sequence[int]
MacVersion = Tuple[int, int]

BuildTag = Union[Tuple[()], Tuple[int, str]]
NormalizedName = NewType("NormalizedName", str)

LocalType = Tuple[Union[int, str], ...]

CmpPrePostDevType = Union[InfinityType, NegativeInfinityType, Tuple[str, int]]
CmpLocalType = Union[
    NegativeInfinityType,
    Tuple[Union[Tuple[int, str], Tuple[NegativeInfinityType, Union[int, str]]], ...],
]
CmpKey = Tuple[
    int,
    Tuple[int, ...],
    CmpPrePostDevType,
    CmpPrePostDevType,
    CmpPrePostDevType,
    CmpLocalType,
]
