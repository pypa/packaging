from __future__ import annotations

import sys
import unittest.mock
from typing import Any

import pytest

from packaging.dependency_groups import (
    CyclicDependencyGroup,
    DependencyGroupInclude,
    DependencyGroupResolver,
    DuplicateGroupNames,
    InvalidDependencyGroupObject,
    resolve_dependency_groups,
)
from packaging.requirements import Requirement

if sys.version_info >= (3, 10):
    from typing import TypeAlias
else:
    from typing_extensions import TypeAlias

GroupsTable: TypeAlias = "dict[str, list[str | dict[str, str]]]"


def test_resolver_init_catches_normalization_conflict() -> None:
    groups: GroupsTable = {"test": ["pytest"], "Test": ["pytest", "coverage"]}
    with pytest.raises(ValueError, match="Duplicate dependency group names"):
        DependencyGroupResolver(groups)


def test_lookup_on_trivial_normalization() -> None:
    groups: GroupsTable = {"test": ["pytest"]}
    resolver = DependencyGroupResolver(groups)
    parsed_group = resolver.lookup("Test")
    assert len(parsed_group) == 1
    assert isinstance(parsed_group[0], Requirement)
    req = parsed_group[0]
    assert req.name == "pytest"


def test_lookup_with_include_result() -> None:
    groups: GroupsTable = {
        "test": ["pytest", {"include-group": "runtime"}],
        "runtime": ["click"],
    }
    resolver = DependencyGroupResolver(groups)
    parsed_group = resolver.lookup("test")
    assert len(parsed_group) == 2

    assert isinstance(parsed_group[0], Requirement)
    assert parsed_group[0].name == "pytest"

    assert isinstance(parsed_group[1], DependencyGroupInclude)
    assert parsed_group[1].include_group == "runtime"


def test_lookup_does_not_trigger_cyclic_include() -> None:
    groups: GroupsTable = {
        "group1": [{"include-group": "group2"}],
        "group2": [{"include-group": "group1"}],
    }
    resolver = DependencyGroupResolver(groups)
    parsed_group = resolver.lookup("group1")
    assert len(parsed_group) == 1

    assert isinstance(parsed_group[0], DependencyGroupInclude)
    assert parsed_group[0].include_group == "group2"


def test_expand_contract_model_only_does_inner_lookup_once() -> None:
    groups: GroupsTable = {
        "root": [
            {"include-group": "mid1"},
            {"include-group": "mid2"},
            {"include-group": "mid3"},
            {"include-group": "mid4"},
        ],
        "mid1": [{"include-group": "contract"}],
        "mid2": [{"include-group": "contract"}],
        "mid3": [{"include-group": "contract"}],
        "mid4": [{"include-group": "contract"}],
        "contract": [{"include-group": "leaf"}],
        "leaf": ["attrs"],
    }
    resolver = DependencyGroupResolver(groups)

    real_inner_resolve = resolver._resolve
    with unittest.mock.patch(
        "packaging.dependency_groups.DependencyGroupResolver._resolve",
        side_effect=real_inner_resolve,
    ) as spy:
        resolved = resolver.resolve("root")
        assert len(resolved) == 4
        assert all(item.name == "attrs" for item in resolved)

        # each of the `mid` nodes will call resolution with `contract`, but only the
        # first of those evaluations should call for resolution of `leaf` -- after that,
        # `contract` will be in the cache and `leaf` will not need to be resolved
        spy.assert_any_call("leaf", "root")
        leaf_calls = [c for c in spy.mock_calls if c.args[0] == "leaf"]
        assert len(leaf_calls) == 1


def test_no_double_parse() -> None:
    groups: GroupsTable = {
        "test": [{"include-group": "runtime"}],
        "runtime": ["click"],
    }
    resolver = DependencyGroupResolver(groups)

    parse = resolver.lookup("test")
    assert len(parse) == 1
    assert isinstance(parse[0], DependencyGroupInclude)
    assert parse[0].include_group == "runtime"

    mock_include = DependencyGroupInclude(include_group="perfidy")

    with unittest.mock.patch(
        "packaging.dependency_groups.DependencyGroupInclude",
        return_value=mock_include,
    ):
        # rerunning with that resolver will not re-resolve
        reparse = resolver.lookup("test")
        assert len(reparse) == 1
        assert isinstance(reparse[0], DependencyGroupInclude)
        assert reparse[0].include_group == "runtime"

        # but verify that a fresh resolver (no cache) will get the mock
        deceived_resolver = DependencyGroupResolver(groups)
        deceived_parse = deceived_resolver.lookup("test")
        assert len(deceived_parse) == 1
        assert isinstance(deceived_parse[0], DependencyGroupInclude)
        assert deceived_parse[0].include_group == "perfidy"


@pytest.mark.parametrize("group_name_declared", ["foo-bar", "foo_bar", "foo..bar"])
@pytest.mark.parametrize("group_name_used", ["foo-bar", "foo_bar", "foo..bar"])
def test_normalized_name_is_used_for_include_group_lookups(
    group_name_declared: str, group_name_used: str
) -> None:
    groups: GroupsTable = {
        group_name_declared: ["spam"],
        "eggs": [{"include-group": group_name_used}],
    }
    resolver = DependencyGroupResolver(groups)

    result = resolver.resolve("eggs")
    assert len(result) == 1
    assert isinstance(result[0], Requirement)
    req = result[0]
    assert req.name == "spam"


def test_empty_group() -> None:
    groups: GroupsTable = {"test": []}
    assert resolve_dependency_groups(groups, "test") == ()


def test_str_list_group() -> None:
    groups: GroupsTable = {"test": ["pytest"]}
    assert resolve_dependency_groups(groups, "test") == ("pytest",)


def test_single_include_group() -> None:
    groups: GroupsTable = {
        "test": [
            "pytest",
            {"include-group": "runtime"},
        ],
        "runtime": ["sqlalchemy"],
    }
    assert set(resolve_dependency_groups(groups, "test")) == {"pytest", "sqlalchemy"}


def test_sdual_include_group() -> None:
    groups: GroupsTable = {
        "test": [
            "pytest",
        ],
        "runtime": ["sqlalchemy"],
    }
    assert set(resolve_dependency_groups(groups, "test", "runtime")) == {
        "pytest",
        "sqlalchemy",
    }


def test_normalized_group_name() -> None:
    groups: GroupsTable = {
        "TEST": ["pytest"],
    }
    assert resolve_dependency_groups(groups, "test") == ("pytest",)


def test_no_such_group_name() -> None:
    groups: GroupsTable = {
        "test": ["pytest"],
    }
    with pytest.raises(LookupError, match="'testing' not found"):
        resolve_dependency_groups(groups, "testing")


def test_duplicate_normalized_name() -> None:
    groups: GroupsTable = {
        "test": ["pytest"],
        "TEST": ["nose2"],
    }
    with pytest.raises(
        DuplicateGroupNames,
        match=r"Duplicate dependency group names: test \((test, TEST)|(TEST, test)\)",
    ):
        resolve_dependency_groups(groups, "test")


def test_cyclic_include() -> None:
    groups: GroupsTable = {
        "group1": [
            {"include-group": "group2"},
        ],
        "group2": [
            {"include-group": "group1"},
        ],
    }
    with pytest.raises(
        CyclicDependencyGroup,
        match=(
            "Cyclic dependency group include while resolving group1: "
            "group1 -> group2, group2 -> group1"
        ),
    ):
        resolve_dependency_groups(groups, "group1")


def test_cyclic_include_many_steps() -> None:
    groups: GroupsTable = {}
    for i in range(100):
        groups[f"group{i}"] = [{"include-group": f"group{i + 1}"}]
    groups["group100"] = [{"include-group": "group0"}]
    with pytest.raises(
        CyclicDependencyGroup,
        match="Cyclic dependency group include while resolving group0:",
    ):
        resolve_dependency_groups(groups, "group0")


def test_cyclic_include_self() -> None:
    groups: GroupsTable = {
        "group1": [
            {"include-group": "group1"},
        ],
    }
    with pytest.raises(
        CyclicDependencyGroup,
        match=(
            "Cyclic dependency group include while resolving group1: "
            "group1 includes itself"
        ),
    ):
        resolve_dependency_groups(groups, "group1")


def test_cyclic_include_ring_under_root() -> None:
    groups: GroupsTable = {
        "root": [
            {"include-group": "group1"},
        ],
        "group1": [
            {"include-group": "group2"},
        ],
        "group2": [
            {"include-group": "group1"},
        ],
    }
    with pytest.raises(
        CyclicDependencyGroup,
        match=(
            "Cyclic dependency group include while resolving root: "
            "group1 -> group2, group2 -> group1"
        ),
    ):
        resolve_dependency_groups(groups, "root")


# a string is a Sequence[str] but is explicitly checked and rejected
def test_non_str_data() -> None:
    groups: Any = {"test": "pytest, coverage"}
    with pytest.raises(
        TypeError,
        match=r"Dependency group 'test' contained a string rather than a list.",
    ):
        resolve_dependency_groups(groups, "test")


def test_non_list_data() -> None:
    groups: Any = {"test": 101}
    with pytest.raises(
        TypeError, match=r"Dependency group 'test' is not a sequence type."
    ):
        resolve_dependency_groups(groups, "test")


@pytest.mark.parametrize(
    "item",
    [
        {},
        {"foo": "bar"},
        {"include-group": "testing", "foo": "bar"},
    ],
)
def test_unknown_object_shape(item: dict[str, str] | object) -> None:
    groups: Any = {"test": [item]}
    with pytest.raises(
        InvalidDependencyGroupObject, match="Invalid dependency group item:"
    ):
        resolve_dependency_groups(groups, "test")


def test_non_unexpected_item_type() -> None:
    groups: Any = {"test": [object()]}
    with pytest.raises(TypeError, match="Invalid dependency group item"):
        resolve_dependency_groups(groups, "test")


def test_dependency_group_include_repr() -> None:
    include = DependencyGroupInclude("test")
    assert repr(include) == "<DependencyGroupInclude('test')>"
