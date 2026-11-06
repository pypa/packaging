"""Regression tests: deeply nested license-expression parentheses must raise a clean
InvalidLicenseExpression, not an uncaught MemoryError / RecursionError (CWE-674)."""

import pytest

from packaging.licenses import (
    MAX_LICENSE_NESTING,
    InvalidLicenseExpression,
    canonicalize_license_expression,
)


def _nested_valid(n: int) -> str:
    # A genuinely nested, grammatically valid compound expression.
    return "(MIT OR " * n + "MIT" + ")" * n


def test_deeply_nested_license_raises_invalid_not_memory_or_recursion_error():
    with pytest.raises(InvalidLicenseExpression):
        canonicalize_license_expression(_nested_valid(MAX_LICENSE_NESTING + 500))


def test_one_over_the_limit_is_rejected_cleanly():
    with pytest.raises(InvalidLicenseExpression):
        canonicalize_license_expression(_nested_valid(MAX_LICENSE_NESTING + 1))


def test_ordinary_license_expressions_unaffected():
    assert canonicalize_license_expression("MIT") == "MIT"
    assert (
        canonicalize_license_expression("mit and (apache-2.0 or bsd-2-clause)")
        == "MIT AND (Apache-2.0 OR BSD-2-Clause)"
    )
