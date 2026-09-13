# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.
from __future__ import annotations

import pytest

from packaging.dependency_groups import resolve_dependency_groups
from packaging.errors import ExceptionGroup


@pytest.fixture
def groups() -> dict[str, list[str | dict[str, str]]]:
    # ``root`` includes two groups: the first contains an invalid requirement,
    # and the second is a wrapper whose own include leads to a second invalid
    # requirement.
    return {
        "root": [{"include-group": "bad"}, {"include-group": "wrapper"}],
        "bad": ["!!! bad invalid"],
        "wrapper": [{"include-group": "also-bad"}],
        "also-bad": ["!!! also invalid"],
    }


def test_error_in_later_sibling_subtree_is_collected(
    groups: dict[str, list[str | dict[str, str]]],
) -> None:
    # An error collected while parsing one group must not stop a later sibling
    # include from being parsed and resolved, so the invalid requirement in
    # ``also-bad`` is reported alongside the one in ``bad``.
    with pytest.raises(ExceptionGroup) as excinfo:
        resolve_dependency_groups(groups, "root")

    messages = [str(e) for e in excinfo.value.exceptions]
    assert len(messages) == 2
    assert "!!! bad invalid" in messages[0]
    assert "!!! also invalid" in messages[1]


def test_invalid_group_not_cached_after_sibling_error(
    groups: dict[str, list[str | dict[str, str]]],
) -> None:
    # The same table must fail identically when the invalid subtree is reached
    # through the wrapper alone, confirming both branches are exercised.
    wrapper_only: dict[str, list[str | dict[str, str]]] = {
        "root": [{"include-group": "wrapper"}],
        "wrapper": groups["wrapper"],
        "also-bad": groups["also-bad"],
    }
    with pytest.raises(ExceptionGroup) as excinfo:
        resolve_dependency_groups(wrapper_only, "root")

    assert "!!! also invalid" in str(excinfo.value.exceptions[0])
