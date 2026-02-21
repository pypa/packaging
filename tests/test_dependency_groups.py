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
from packaging.errors import ExceptionGroup
from packaging.requirements import Requirement

if sys.version_info >= (3, 10):
    from typing import TypeAlias
else:
    from typing_extensions import TypeAlias

GroupsTable: TypeAlias = "dict[str, list[str | dict[str, str]]]"


def test_resolver_init_catches_normalization_conflict() -> None:
    groups: GroupsTable = {"test": ["pytest"], "Test": ["pytest", "coverage"]}
    with pytest.raises(
        ExceptionGroup, match=r"\[dependency-groups\] data was invalid"
    ) as excinfo:
        DependencyGroupResolver(groups)

    assert excinfo.group_contains(
        DuplicateGroupNames, match="Duplicate dependency group names"
    )


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
        spy.assert_any_call("leaf", "root", unittest.mock.ANY)
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
    with pytest.raises(
        ExceptionGroup, match=r"\[dependency-groups\] data for 'testing' was malformed"
    ) as excinfo:
        resolve_dependency_groups(groups, "testing")

    assert excinfo.group_contains(LookupError, match="'testing' not found")


def test_duplicate_normalized_name() -> None:
    groups: GroupsTable = {
        "test": ["pytest"],
        "TEST": ["nose2"],
    }
    with pytest.raises(
        ExceptionGroup, match=r"\[dependency-groups\] data was invalid"
    ) as excinfo:
        resolve_dependency_groups(groups, "test")

    assert excinfo.group_contains(
        DuplicateGroupNames,
        match=r"Duplicate dependency group names: test \((test, TEST)|(TEST, test)\)",
    )


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
        ExceptionGroup, match=r"\[dependency-groups\] data for 'group1' was malformed"
    ) as excinfo:
        resolve_dependency_groups(groups, "group1")

    assert excinfo.group_contains(
        CyclicDependencyGroup,
        match=(
            "Cyclic dependency group include while resolving group1: "
            "group1 -> group2, group2 -> group1"
        ),
    )


def test_cyclic_include_many_steps() -> None:
    groups: GroupsTable = {}
    for i in range(100):
        groups[f"group{i}"] = [{"include-group": f"group{i + 1}"}]
    groups["group100"] = [{"include-group": "group0"}]
    with pytest.raises(
        ExceptionGroup, match=r"\[dependency-groups\] data for 'group0' was malformed"
    ) as excinfo:
        resolve_dependency_groups(groups, "group0")

    assert excinfo.group_contains(
        CyclicDependencyGroup,
        match="Cyclic dependency group include while resolving group0: ",
    )


def test_cyclic_include_self() -> None:
    groups: GroupsTable = {
        "group1": [
            {"include-group": "group1"},
        ],
    }

    with pytest.raises(
        ExceptionGroup, match=r"\[dependency-groups\] data for 'group1' was malformed"
    ) as excinfo:
        resolve_dependency_groups(groups, "group1")

    assert excinfo.group_contains(
        CyclicDependencyGroup,
        match=(
            "Cyclic dependency group include while resolving group1: "
            "group1 includes itself"
        ),
    )


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
        ExceptionGroup, match=r"\[dependency-groups\] data for 'root' was malformed"
    ) as excinfo:
        resolve_dependency_groups(groups, "root")

    assert excinfo.group_contains(
        CyclicDependencyGroup,
        match=(
            "Cyclic dependency group include while resolving root: "
            "group1 -> group2, group2 -> group1"
        ),
    )


# each access to a cyclic group should raise an error
def test_cyclic_include_accessed_repeatedly_on_resolver_instance() -> None:
    groups: GroupsTable = {
        "group1": [
            {"include-group": "group2"},
        ],
        "group2": [
            {"include-group": "group1"},
        ],
    }
    resolver = DependencyGroupResolver(groups)

    # each access raises an exception group of the same shape
    for _ in range(3):
        with pytest.raises(
            ExceptionGroup,
            match=r"\[dependency-groups\] data for 'group1' was malformed",
        ) as excinfo:
            resolver.resolve("group1")
        assert excinfo.group_contains(
            CyclicDependencyGroup,
            match=(
                "Cyclic dependency group include while resolving group1: "
                "group1 -> group2, group2 -> group1"
            ),
        )


# a string is a Sequence[str] but is explicitly checked and rejected
def test_non_str_data() -> None:
    groups: Any = {"test": "pytest, coverage"}
    with pytest.raises(
        ExceptionGroup, match=r"\[dependency-groups\] data for 'test' was malformed"
    ) as excinfo:
        resolve_dependency_groups(groups, "test")

    assert excinfo.group_contains(
        TypeError,
        match=r"Dependency group 'test' contained a string rather than a list.",
    )


def test_non_list_data() -> None:
    groups: Any = {"test": 101}
    with pytest.raises(
        ExceptionGroup, match=r"\[dependency-groups\] data for 'test' was malformed"
    ) as excinfo:
        resolve_dependency_groups(groups, "test")

    assert excinfo.group_contains(
        TypeError, match=r"Dependency group 'test' is not a sequence type."
    )


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
        ExceptionGroup, match=r"\[dependency-groups\] data for 'test' was malformed"
    ) as excinfo:
        resolve_dependency_groups(groups, "test")

    assert excinfo.group_contains(
        InvalidDependencyGroupObject, match="Invalid dependency group item:"
    )


def test_non_unexpected_item_type() -> None:
    groups: Any = {"test": [object()]}
    with pytest.raises(
        ExceptionGroup, match=r"\[dependency-groups\] data for 'test' was malformed"
    ) as excinfo:
        resolve_dependency_groups(groups, "test")

    assert excinfo.group_contains(TypeError, match="Invalid dependency group item")


def test_dependency_group_include_repr() -> None:
    include = DependencyGroupInclude("test")
    assert repr(include) == "DependencyGroupInclude('test')"


def test_resolution_can_capture_multiple_errors_at_once() -> None:
    groups: Any = {
        "all": [
            {"include-group": "all-invalid"},
            {"include-group": "all-valid"},
        ],
        "all-valid": [
            {"include-group": "empty"},
            {"include-group": "simple"},
        ],
        "all-invalid": [
            {"include-group": "self-reference"},
            {"include-group": "invalid-object"},
            {"include-group": "invalid-type"},
            {"include-group": "invalid-type"},
        ],
        "self-reference": [{"include-group": "self-reference"}],
        "invalid-object": [{}],
        "invalid-type": "foo",
        "empty": [],
        "simple": ["jsonschema<5"],
    }

    # sanity check: even in the presence of these invalid data, we can extract the valid
    # parts
    valid_resolution = resolve_dependency_groups(groups, "all-valid")
    assert len(valid_resolution) == 1
    assert valid_resolution[0] == "jsonschema<5"

    # however, resolving everything triggers *multiple* errors, from the various
    # incorrect pieces of data, collected in an exception group
    with pytest.raises(
        ExceptionGroup, match=r"\[dependency-groups\] data for 'all' was malformed"
    ) as excinfo:
        resolve_dependency_groups(groups, "all")

    assert excinfo.group_contains(
        CyclicDependencyGroup,
        match=(
            "Cyclic dependency group include while resolving all: "
            "self-reference includes itself"
        ),
    )
    assert excinfo.group_contains(
        TypeError,
        match=r"Dependency group 'invalid-type' contained a string rather than a list.",
    )
