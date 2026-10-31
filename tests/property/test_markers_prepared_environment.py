# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.

"""Check prepared marker evaluation against ordinary evaluation."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from hypothesis import given
from hypothesis import strategies as st

from packaging.markers import (
    Marker,
    UndefinedComparison,
    UndefinedEnvironmentName,
    prepare_environment,
)
from packaging.utils import canonicalize_name

from .strategies import SETTINGS

if TYPE_CHECKING:
    from collections.abc import Callable
    from collections.abc import Set as AbstractSet

    from packaging.markers import EvaluateContext

pytestmark = pytest.mark.property

CONTEXTS: list[EvaluateContext] = ["metadata", "lock_file", "requirement"]

STRING_VARIABLES = ["os_name", "sys_platform", "platform_machine", "platform_system"]
VERSION_VARIABLES = ["python_version", "python_full_version", "implementation_version"]
SET_VARIABLES = ["extras", "dependency_groups"]

STRING_VALUES = ["posix", "nt", "linux", "win32", "x86_64", "Linux"]
VERSION_VALUES = ["3", "3.10", "3.10.4", "3.11.0a5", "2.7"]
EXTRA_VALUES = ["Fancy.Feature", "fancy-feature", "docs", "Test_Extra"]
COMPARISONS = ["==", "!=", "<", "<=", ">", ">="]

contexts = st.sampled_from(CONTEXTS)


@st.composite
def marker_atoms(draw: st.DrawFn) -> str:
    """One comparison or membership test, as marker source."""
    kind = draw(st.sampled_from(["string", "version", "extra", "membership"]))

    if kind == "string":
        variable = draw(st.sampled_from(STRING_VARIABLES))
        value = draw(st.sampled_from(STRING_VALUES))
    elif kind == "version":
        variable = draw(st.sampled_from(VERSION_VARIABLES))
        value = draw(st.sampled_from(VERSION_VALUES))
    elif kind == "extra":
        variable = "extra"
        value = draw(st.sampled_from(EXTRA_VALUES))
    else:
        member = draw(st.sampled_from(EXTRA_VALUES))
        return f'"{member}" in {draw(st.sampled_from(SET_VARIABLES))}'

    return f'{variable} {draw(st.sampled_from(COMPARISONS))} "{value}"'


@st.composite
def markers(draw: st.DrawFn) -> Marker:
    """One to three atoms joined by ``and`` / ``or``, some of them grouped."""
    source = draw(marker_atoms())
    for _ in range(draw(st.integers(min_value=0, max_value=2))):
        joiner = draw(st.sampled_from(["and", "or"]))
        atom = draw(marker_atoms())
        left = f"({source})" if draw(st.booleans()) else source
        source = f"{left} {joiner} {atom}"
    return Marker(source)


@st.composite
def environments(draw: st.DrawFn) -> dict[str, str | AbstractSet[str]] | None:
    """Environment overrides, including Python build versions needing repair."""
    if draw(st.booleans()):
        return None

    environment: dict[str, str | AbstractSet[str]] = {}
    for key in draw(st.sets(st.sampled_from([*STRING_VARIABLES, "nonsense"]))):
        environment[key] = draw(st.sampled_from(STRING_VALUES))
    for key in draw(st.sets(st.sampled_from(VERSION_VARIABLES))):
        values = VERSION_VALUES
        if key == "python_full_version":
            values = [*VERSION_VALUES, "3.11.1+"]
        environment[key] = draw(st.sampled_from(values))
    for key in draw(st.sets(st.sampled_from(SET_VARIABLES))):
        environment[key] = frozenset(draw(st.sets(st.sampled_from(EXTRA_VALUES))))
    if draw(st.booleans()):
        environment["extra"] = draw(st.sampled_from([*EXTRA_VALUES, ""]))

    return environment


def outcome(evaluate: Callable[[], bool]) -> bool | type[Exception]:
    """Run evaluate, returning its result or the class of the error it raised."""
    try:
        return evaluate()
    except (UndefinedComparison, UndefinedEnvironmentName) as exc:
        return type(exc)


@given(
    marker=markers(),
    environment=environments(),
    context=contexts,
    extra=st.none() | st.sampled_from(EXTRA_VALUES),
)
@SETTINGS
def test_prepared_evaluation_matches_ordinary_evaluation(
    marker: Marker,
    environment: dict[str, str | AbstractSet[str]] | None,
    context: EvaluateContext,
    extra: str | None,
) -> None:
    prepared = prepare_environment(environment, context)
    if extra is not None:
        prepared["extra"] = canonicalize_name(extra)
        environment = {**(environment or {}), "extra": extra}

    assert outcome(lambda: marker.evaluate_prepared(prepared)) == outcome(
        lambda: marker.evaluate(environment, context)
    )
