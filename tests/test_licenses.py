import pytest

from packaging.licenses import (
    _MAX_LICENSE_NESTING,
    InvalidLicenseExpression,
    canonicalize_license_expression,
)
from packaging.licenses._spdx import EXCEPTIONS, LICENSES


def test_licenses() -> None:
    for license_id in LICENSES:
        assert license_id == license_id.lower()


def test_exceptions() -> None:
    for exception_id in EXCEPTIONS:
        assert exception_id == exception_id.lower()


def test_licenseref_plus_suffix_is_invalid() -> None:
    with pytest.raises(InvalidLicenseExpression, match="Invalid licenseref"):
        canonicalize_license_expression("LicenseRef-Foo+")


@pytest.mark.parametrize(
    "license_expression",
    [
        "MIT WITH Classpath-exception-2.0 WITH GCC-exception-3.1",
        "(MIT) WITH Classpath-exception-2.0",
        "(MIT OR Apache-2.0) WITH Classpath-exception-2.0",
        "LicenseRef-",
    ],
)
def test_invalid_spdx_with_or_licenseref_forms(license_expression: str) -> None:
    with pytest.raises(InvalidLicenseExpression):
        canonicalize_license_expression(license_expression)


@pytest.mark.parametrize(
    ("license_expression", "expected"),
    [
        ("LicenseRef-mit OR licenseref-MIT", "LicenseRef-mit OR LicenseRef-mit"),
        ("licenseref-MIT AND LicenseRef-mit", "LicenseRef-MIT AND LicenseRef-MIT"),
        (
            "(LICENSEREF-Foo OR licenseref-foo) AND MIT AND LicenseRef-FOO",
            "(LicenseRef-Foo OR LicenseRef-Foo) AND MIT AND LicenseRef-Foo",
        ),
        ("licenseref-public-domain", "LicenseRef-public-domain"),
    ],
)
def test_licenseref_case_variants_use_first_spelling(
    license_expression: str, expected: str
) -> None:
    assert canonicalize_license_expression(license_expression) == expected


@pytest.mark.parametrize(
    "license_expression",
    [
        "LicenseRef-\u212austom",
        "licenseref-Custom\u212a",
        "LicenseRef-\u212austom AND MIT",
        "MIT OR LicenseRef-\u212austom",
        "MIT AND (LicenseRef-\u212austom OR Apache-2.0)",
        "LicenseRef-Kustom OR LicenseRef-\u212austom",
        "LicenseRef-\u212austom OR LicenseRef-Kustom",
    ],
)
def test_licenseref_rejects_kelvin_sign(license_expression: str) -> None:
    # The Kelvin sign becomes ASCII k when lowercased, but is not an SPDX ALPHA.
    with pytest.raises(InvalidLicenseExpression, match="non-ASCII"):
        canonicalize_license_expression(license_expression)


@pytest.mark.parametrize(
    ("license_expression", "expected"),
    [
        ("lIcEnSeReF-Kustom.123-aB", "LicenseRef-Kustom.123-aB"),
        (
            "mit aNd (LICENSEREF-Kustom.123-aB oR apache-2.0)",
            "MIT AND (LicenseRef-Kustom.123-aB OR Apache-2.0)",
        ),
        (
            "licenseref-Kustom OR LICENSEREF-kUSTOM",
            "LicenseRef-Kustom OR LicenseRef-Kustom",
        ),
    ],
)
def test_ascii_licenseref_preserves_spelling(
    license_expression: str, expected: str
) -> None:
    assert canonicalize_license_expression(license_expression) == expected


def test_nesting_at_limit() -> None:
    depth = _MAX_LICENSE_NESTING
    expression = "(MIT OR " * depth + "MIT" + ")" * depth
    assert canonicalize_license_expression(expression) == expression


@pytest.mark.parametrize("depth", [_MAX_LICENSE_NESTING + 1, 10_000])
def test_invalid_too_deeply_nested(depth: int) -> None:
    # Deep nesting must be reported as InvalidLicenseExpression, not MemoryError.
    with pytest.raises(InvalidLicenseExpression):
        canonicalize_license_expression("(MIT OR " * depth + "MIT" + ")" * depth)
