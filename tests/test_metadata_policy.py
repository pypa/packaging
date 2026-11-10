# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.

from __future__ import annotations

import pickle
import sys
from collections import Counter
from types import ModuleType, SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import Mock

import pytest

from packaging.errors import ExceptionGroup
from packaging.metadata import InvalidMetadata, Metadata
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.version import Version

if TYPE_CHECKING:
    from collections.abc import Callable

    from packaging.metadata import RawMetadata


@pytest.fixture(params=["raw", "text", "bytes"])
def source(request: pytest.FixtureRequest) -> str:
    return str(request.param)


def make_metadata(
    source: str,
    policy: object | None,
    *,
    validate: bool = True,
    data: RawMetadata | None = None,
) -> Metadata:
    if data is None:
        data = {"metadata_version": "2.4", "name": "example", "version": "1.0"}
    if source == "raw":
        return Metadata.from_raw(data, validate=validate, validation_policy=policy)
    headers: list[str] = []
    for key, value in data.items():
        field = {
            "requires_dist": "Requires-Dist",
            "provides_extra": "Provides-Extra",
            "license_files": "License-File",
        }.get(key, key.replace("_", "-"))
        values = value if isinstance(value, list) else [value]
        headers.extend(f"{field}: {item}" for item in values)
    text = "\n".join(headers) + "\n"
    return Metadata.from_email(
        text.encode() if source == "bytes" else text,
        validate=validate,
        validation_policy=policy,
    )


def reject(error: Exception) -> Callable[[object], None]:
    def validator(value: object) -> None:
        del value
        raise error

    return validator


def fields(group: ExceptionGroup) -> Counter[str]:
    result: Counter[str] = Counter()
    for error in group.exceptions:
        assert isinstance(error, InvalidMetadata)
        result[error.field] += 1
    return result


@pytest.mark.parametrize("validate", [False, True])
def test_enriched_values_and_successful_cache(source: str, validate: bool) -> None:
    seen: list[tuple[str, object]] = []

    class Policy:
        def validate_version(self, value: Version) -> None:
            seen.append(("version", value))

        def validate_requires_python(self, value: SpecifierSet | None) -> None:
            seen.append(("requires_python", value))

        def validate_requires_dist(self, value: list[Requirement] | None) -> None:
            seen.append(("requires_dist", value))

        def validate_provides_extra(self, value: list[str] | None) -> None:
            seen.append(("provides_extra", value))

        def validate_summary(self, value: str | None) -> None:
            seen.append(("summary", value))

    data: RawMetadata = {
        "metadata_version": "2.4",
        "name": "example",
        "version": "01.0",
        "requires_python": ">=3.10",
        "requires_dist": ["dependency>=1"],
        "provides_extra": ["Test_Extra"],
    }
    result = make_metadata(source, Policy(), data=data, validate=validate)
    assert bool(seen) == validate
    for _ in range(2):
        assert result.version == Version("1.0")
        assert result.requires_python == SpecifierSet(">=3.10")
        assert result.requires_dist == [Requirement("dependency>=1")]
        assert result.provides_extra == ["test-extra"]
        assert result.summary is None
    assert dict(seen) == {
        "version": Version("1.0"),
        "requires_python": SpecifierSet(">=3.10"),
        "requires_dist": [Requirement("dependency>=1")],
        "provides_extra": ["test-extra"],
        "summary": None,
    }
    assert len(seen) == 5
    assert data["version"] == "01.0"


@pytest.mark.parametrize("grouped", [False, True])
def test_lazy_rejection_is_not_cached(source: str, grouped: bool) -> None:
    invalid = InvalidMetadata("version", "private versions are forbidden")
    error = ExceptionGroup("policy", [invalid]) if grouped else invalid
    policy = SimpleNamespace(validate_version=reject(error))
    result = make_metadata(source, policy, validate=False)
    for _ in range(2):
        with pytest.raises(type(error)) as exc_info:
            result.version  # noqa: B018
        assert exc_info.value is error
    policy.validate_version = lambda _value: None
    assert result.version == Version("1.0")


@pytest.mark.parametrize("field", ["summary", "license_files"])
def test_policy_can_require_absent_optional_field(source: str, field: str) -> None:
    error = InvalidMetadata(field.replace("_", "-"), "required by application")
    policy = SimpleNamespace(**{f"validate_{field}": reject(error)})
    # Absent License-File is not a version-age violation in Metadata 1.0.
    data: RawMetadata = {"metadata_version": "1.0", "name": "example", "version": "1"}
    with pytest.raises(ExceptionGroup) as exc_info:
        make_metadata(source, policy, data=data)
    assert list(exc_info.value.exceptions) == [error]


def test_core_and_nested_policy_errors_are_aggregated(source: str) -> None:
    first = InvalidMetadata("summary", "one")
    second = InvalidMetadata("summary", "two")
    policy = SimpleNamespace(
        validate_summary=reject(
            ExceptionGroup("policy", [first, ExceptionGroup("nested", [second])])
        )
    )
    with pytest.raises(ExceptionGroup) as exc_info:
        make_metadata(
            source,
            policy,
            data={"metadata_version": "2.4", "name": "bad name", "version": "bad"},
        )
    assert fields(exc_info.value) == Counter({"name": 1, "version": 1, "summary": 2})
    assert first in exc_info.value.exceptions
    assert second in exc_info.value.exceptions


@pytest.mark.parametrize("grouped", [False, True])
def test_metadata_version_policy_preserves_age_checks(
    source: str, grouped: bool
) -> None:
    error = InvalidMetadata("metadata-version", "unsupported by application")
    policy_error = ExceptionGroup("policy", [error]) if grouped else error
    policy = SimpleNamespace(validate_metadata_version=reject(policy_error))
    with pytest.raises(ExceptionGroup) as exc_info:
        make_metadata(
            source,
            policy,
            data={
                "metadata_version": "1.0",
                "name": "example",
                "version": "1",
                "requires_python": ">=3.10",
            },
        )
    assert fields(exc_info.value) == Counter(
        {"metadata-version": 1, "requires-python": 1}
    )
    assert error in exc_info.value.exceptions
    assert any(
        "introduced in metadata version 1.2" in str(e)
        for e in exc_info.value.exceptions
    )


@pytest.mark.parametrize("validate", [False, True])
@pytest.mark.parametrize("field", ["version", "metadata_version"])
def test_invalid_core_value_is_not_given_to_policy(
    source: str, validate: bool, field: str
) -> None:
    policy = SimpleNamespace(**{f"validate_{field}": reject(AssertionError("called"))})
    data: RawMetadata = {"metadata_version": "2.4", "name": "example", "version": "1"}
    data[field] = "invalid"  # type: ignore[literal-required]
    if validate:
        with pytest.raises(ExceptionGroup) as exc_info:
            make_metadata(source, policy, data=data)
        assert fields(exc_info.value) == Counter({field.replace("_", "-"): 1})
    else:
        result = make_metadata(source, policy, data=data, validate=False)
        with pytest.raises(InvalidMetadata):
            getattr(result, field)


@pytest.mark.parametrize(
    "method", ["validate_name", "validate_metadata_version", "full_validate"]
)
@pytest.mark.parametrize("kind", ["ordinary", "mixed-group", "nested-mixed-group"])
def test_policy_programming_errors_propagate(
    source: str, method: str, kind: str
) -> None:
    problem = RuntimeError("broken policy")
    error: Exception = problem
    if kind != "ordinary":
        error = ExceptionGroup("mixed", [InvalidMetadata("name", "invalid"), problem])
    if kind == "nested-mixed-group":
        error = ExceptionGroup("outer", [error])
    policy = SimpleNamespace(**{method: reject(error)})
    with pytest.raises(type(error)) as exc_info:
        make_metadata(source, policy)
    assert exc_info.value is error


@pytest.mark.parametrize("validate", [False, True])
@pytest.mark.parametrize(
    "returned", [False, True, InvalidMetadata("version", "returned")]
)
def test_policy_must_raise_and_return_none(
    source: str, validate: bool, returned: object
) -> None:
    policy = SimpleNamespace(validate_version=lambda _value: returned)
    with pytest.raises(TypeError, match="must return None"):
        make_metadata(source, policy, validate=validate).version  # noqa: B018


@pytest.mark.parametrize(
    "policy", [None, object(), SimpleNamespace(validate_version=None)]
)
def test_policy_methods_are_optional(source: str, policy: object | None) -> None:
    result = make_metadata(source, policy)
    assert result.version == Version("1.0")


def test_full_validation_receives_validated_metadata(source: str) -> None:
    calls: list[str] = []

    class Policy:
        def validate_version(self, value: Version) -> None:
            assert value == Version("1.0")
            calls.append("field")

        def full_validate(self, value: Metadata) -> None:
            assert value.name == "example"
            assert value.version == Version("1.0")
            assert value.summary is None
            calls.append("full")

    result = make_metadata(source, Policy())
    assert calls == ["field", "full"]
    assert result.version == Version("1.0")
    assert calls == ["field", "full"]


@pytest.mark.parametrize("grouped", [False, True])
def test_full_validation_errors(source: str, grouped: bool) -> None:
    error = InvalidMetadata("summary", "summary required for this project")
    cause = ValueError("application configuration")
    error.__cause__ = cause
    raised = (
        ExceptionGroup("outer", [ExceptionGroup("inner", [error])])
        if grouped
        else error
    )
    with pytest.raises(ExceptionGroup) as exc_info:
        make_metadata(source, SimpleNamespace(full_validate=reject(raised)))
    assert list(exc_info.value.exceptions) == [error]
    assert error.__cause__ is cause


def test_full_validation_must_return_none(source: str) -> None:
    with pytest.raises(TypeError, match="'full_validate' must return None"):
        make_metadata(source, SimpleNamespace(full_validate=lambda _value: False))


@pytest.mark.parametrize("failure", ["core", "policy"])
def test_full_validation_skipped_after_field_failure(source: str, failure: str) -> None:
    policy = SimpleNamespace(full_validate=reject(AssertionError("full called")))
    data: RawMetadata = {"metadata_version": "2.4", "name": "example", "version": "1"}
    if failure == "core":
        data["version"] = "invalid"
    else:
        policy.validate_version = reject(InvalidMetadata("version", "policy"))
    with pytest.raises(ExceptionGroup) as exc_info:
        make_metadata(source, policy, data=data)
    assert fields(exc_info.value) == Counter({"version": 1})


def test_lazy_metadata_does_not_run_full_validation(source: str) -> None:
    policy = SimpleNamespace(full_validate=reject(AssertionError("full called")))
    result = make_metadata(source, policy, validate=False)
    assert result.name == "example"
    assert result.version == Version("1.0")
    assert result.metadata_version == "2.4"


@pytest.mark.parametrize("header", ["Unknown-Field: x", "Summary: one\nSummary: two"])
def test_email_parse_errors_skip_full_validation(header: str) -> None:
    policy = SimpleNamespace(full_validate=reject(AssertionError("full called")))
    with pytest.raises(ExceptionGroup) as exc_info:
        Metadata.from_email(
            f"Metadata-Version: 2.4\nName: example\nVersion: 1\n{header}\n",
            validation_policy=policy,
        )
    assert fields(exc_info.value) == Counter({header.partition(":")[0].lower(): 1})


def test_email_parse_core_and_policy_errors_are_aggregated() -> None:
    policy_error = InvalidMetadata("summary", "policy")
    with pytest.raises(ExceptionGroup) as exc_info:
        Metadata.from_email(
            "Metadata-Version: 2.4\nName: example\nVersion: bad\nUnknown: x\n",
            validation_policy=SimpleNamespace(validate_summary=reject(policy_error)),
        )
    assert fields(exc_info.value) == Counter({"unknown": 1, "version": 1, "summary": 1})
    assert policy_error in exc_info.value.exceptions


def test_email_unparsed_field_keeps_policy_error() -> None:
    policy_error = InvalidMetadata("summary", "policy")
    with pytest.raises(ExceptionGroup) as exc_info:
        Metadata.from_email(
            "Metadata-Version: 2.4\nName: example\nVersion: 1.0\n"
            "Summary: a\nSummary: b\n",
            validation_policy=SimpleNamespace(validate_summary=reject(policy_error)),
        )
    assert fields(exc_info.value) == Counter({"summary": 2})
    assert policy_error in exc_info.value.exceptions


def test_foreign_exception_group_is_aggregated(
    source: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    class ForeignGroup(Exception):
        def __init__(self, message: str, exceptions: list[Exception]) -> None:
            super().__init__(message, exceptions)
            self.exceptions = tuple(exceptions)

    module = ModuleType("exceptiongroup")
    module.ExceptionGroup = ForeignGroup  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "exceptiongroup", module)
    policy_error = InvalidMetadata("version", "policy")
    policy = SimpleNamespace(
        validate_version=reject(ForeignGroup("x", [policy_error])),
        validate_name=reject(InvalidMetadata("name", "policy")),
    )
    with pytest.raises(ExceptionGroup) as exc_info:
        make_metadata(source, policy)
    assert fields(exc_info.value) == Counter({"version": 1, "name": 1})
    assert policy_error in exc_info.value.exceptions


def test_exception_group_without_backport(
    source: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delitem(sys.modules, "exceptiongroup", raising=False)
    policy_error = InvalidMetadata("version", "policy")
    policy = SimpleNamespace(
        validate_version=reject(ExceptionGroup("x", [policy_error]))
    )
    with pytest.raises(ExceptionGroup) as exc_info:
        make_metadata(source, policy)
    assert list(exc_info.value.exceptions) == [policy_error]


class DynamicPolicy:
    def __getattr__(self, name: str) -> Callable[[object], object]:
        return lambda _value: AssertionError(name)


@pytest.mark.parametrize("policy", [Mock(), DynamicPolicy()])
def test_dynamic_attributes_are_not_policy_methods(source: str, policy: object) -> None:
    assert make_metadata(source, policy).version == Version("1.0")
    assert make_metadata(source, policy, validate=False).version == Version("1.0")


def test_policies_are_isolated_per_instance(source: str) -> None:
    rejected = make_metadata(
        source,
        SimpleNamespace(validate_version=reject(InvalidMetadata("version", "policy"))),
        validate=False,
    )
    accepted = make_metadata(source, object(), validate=False)
    with pytest.raises(InvalidMetadata):
        rejected.version  # noqa: B018
    assert accepted.version == Version("1.0")
    assert make_metadata(source, None).version == Version("1.0")


class PublicVersionPolicy:
    def validate_version(self, value: Version) -> None:
        if value.local is not None:
            raise InvalidMetadata("version", "local versions are forbidden")


def test_pickle_retains_lazy_policy(source: str) -> None:
    result = make_metadata(
        source,
        PublicVersionPolicy(),
        validate=False,
        data={"metadata_version": "2.4", "name": "example", "version": "1+private"},
    )
    restored = pickle.loads(pickle.dumps(result))
    with pytest.raises(InvalidMetadata, match="local versions are forbidden"):
        restored.version  # noqa: B018


def test_serialization_drops_policy_keeps_values(source: str) -> None:
    result = make_metadata(source, PublicVersionPolicy(), validate=False)
    restored = Metadata.from_email(result.as_rfc822().as_bytes())
    assert restored.version == Version("1.0")
    assert restored.name == "example"
