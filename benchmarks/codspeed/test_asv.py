# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.

"""Run the asv benchmark suites with pytest-codspeed.

This directory has no ``__init__.py``, so asv does not import it.
"""

# ruff: noqa: INP001

from __future__ import annotations

import importlib
import inspect
import pkgutil
from typing import TYPE_CHECKING, Any

import pytest

import benchmarks

if TYPE_CHECKING:
    from collections.abc import Callable

    from pytest_codspeed import BenchmarkFixture


def _cases() -> list[Any]:
    cases = []
    for info in pkgutil.iter_modules(benchmarks.__path__):
        mod = importlib.import_module(f"benchmarks.{info.name}")
        for cls_name, cls in inspect.getmembers(mod, inspect.isclass):
            if cls.__module__ != mod.__name__:
                continue
            for name, fn in inspect.getmembers(cls, inspect.isfunction):
                if not name.startswith("time_"):
                    continue
                for param in getattr(fn, "params", [()]):
                    args = () if param == () else (param,)
                    suffix = f"[{param}]" if args else ""
                    cases.append(
                        pytest.param(cls, name, args, id=f"{cls_name}.{name}{suffix}")
                    )
    return cases


@pytest.mark.parametrize(("cls", "name", "args"), _cases())
def test_benchmark(
    benchmark: BenchmarkFixture, cls: type, name: str, args: tuple[Any, ...]
) -> None:
    def setup() -> tuple[tuple[Any, ...], dict[str, Any]]:
        obj = cls()
        if hasattr(obj, "setup"):
            obj.setup(*args)
        return (getattr(obj, name), *args), {}

    def call(func: Callable[..., object], *func_args: object) -> None:
        func(*func_args)

    if getattr(getattr(cls, name), "number", None) == 1:
        # Cold benchmarks need new state for each round and no warmup.
        benchmark.pedantic(call, setup=setup, rounds=10, warmup_rounds=0)
    else:
        (func, *func_args), _ = setup()
        benchmark(func, *func_args)
