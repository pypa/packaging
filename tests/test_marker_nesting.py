"""Regression tests: deeply nested marker parentheses must raise a clean
InvalidMarker / InvalidRequirement, not a RecursionError (CWE-674)."""

import pytest

from packaging._parser import MAX_MARKER_NESTING
from packaging.markers import InvalidMarker, Marker
from packaging.requirements import InvalidRequirement, Requirement


def _nested(n: int) -> str:
    return "(" * n + "python_version > '1'" + ")" * n


def test_deeply_nested_marker_raises_invalid_marker_not_recursion_error():
    # Well beyond MAX_MARKER_NESTING and beyond the old crashing threshold.
    with pytest.raises(InvalidMarker):
        Marker(_nested(MAX_MARKER_NESTING + 1000))


def test_deeply_nested_requirement_marker_raises_invalid_requirement():
    with pytest.raises(InvalidRequirement):
        Requirement("pkg; " + _nested(MAX_MARKER_NESTING + 1000))


def test_nesting_at_the_limit_still_parses():
    # Nesting up to the limit remains valid (no false positives on real markers,
    # which are far shallower than the limit).
    assert Marker(_nested(MAX_MARKER_NESTING)) is not None


def test_one_over_the_limit_is_rejected_cleanly():
    with pytest.raises(InvalidMarker):
        Marker(_nested(MAX_MARKER_NESTING + 1))


def test_ordinary_markers_unaffected():
    # Realistic markers (shallow nesting) keep working exactly as before.
    assert Marker("python_version >= '3.8'") is not None
    assert Marker("(python_version >= '3.8' and sys_platform == 'linux')") is not None
    assert Marker(
        "python_version >= '3.8' or (os_name == 'posix' and sys_platform == 'linux')"
    ) is not None
