import pytest

from packaging.licenses import (
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


@pytest.mark.parametrize("depth", [199, 200])
@pytest.mark.parametrize("license_expression", ["MIT", "MIT AND Apache-2.0"])
def test_license_parentheses_within_nesting_limit(
    depth: int, license_expression: str
) -> None:
    expression = "(" * depth + license_expression + ")" * depth
    assert canonicalize_license_expression(expression) == expression


@pytest.mark.parametrize("depth", [201, 1000])
@pytest.mark.parametrize("license_expression", ["MIT", "MIT AND Apache-2.0"])
def test_license_parentheses_exceed_nesting_limit(
    depth: int, license_expression: str
) -> None:
    expression = "(" * depth + license_expression + ")" * depth
    with pytest.raises(InvalidLicenseExpression) as exc_info:
        canonicalize_license_expression(expression)

    assert str(exc_info.value) == f"Invalid license expression: {expression!r}"


def test_license_parenthesis_limit_is_per_group() -> None:
    group = "(" * 200 + "MIT" + ")" * 200
    expression = f"{group} OR {group}"
    assert canonicalize_license_expression(expression) == expression


@pytest.mark.parametrize(
    ("license_expression", "expected"),
    [
        ("mIt", "MIT"),
        ("APACHE-2.0", "Apache-2.0"),
        (
            "gpl-2.0-only with classpath-exception-2.0",
            "GPL-2.0-only WITH Classpath-exception-2.0",
        ),
        ("apache-2.0 WITH llvm-exception", "Apache-2.0 WITH LLVM-exception"),
        ("GPL-2.0-ONLY WITH GCC-EXCEPTION-3.1", "GPL-2.0-only WITH GCC-exception-3.1"),
        (
            "(mit with classpath-exception-2.0 or apache-2.0) and bsd-3-clause",
            "(MIT WITH Classpath-exception-2.0 OR Apache-2.0) AND BSD-3-Clause",
        ),
        (
            "mit aNd apache-2.0 oR bsd-3-clause",
            "MIT AND Apache-2.0 OR BSD-3-Clause",
        ),
        (
            "(mit OR apache-2.0)AND(bsd-3-clause OR gpl-2.0-only)",
            "(MIT OR Apache-2.0) AND (BSD-3-Clause OR GPL-2.0-only)",
        ),
        ("mit\tand\napache-2.0", "MIT AND Apache-2.0"),
        ("  ((mit))  ", "((MIT))"),
    ],
)
def test_normalize_license_expression(license_expression: str, expected: str) -> None:
    assert canonicalize_license_expression(license_expression) == expected


@pytest.mark.parametrize(
    "license_expression",
    [
        pytest.param(" ", id="whitespace-only"),
        pytest.param("()", id="empty-group"),
        pytest.param("MIT Apache-2.0", id="adjacent-licenses"),
        pytest.param("MIT (Apache-2.0)", id="license-before-group"),
        pytest.param("(MIT) Apache-2.0", id="group-before-license"),
        pytest.param("(MIT)(Apache-2.0)", id="adjacent-groups"),
        pytest.param(") MIT (", id="closing-before-opening"),
        pytest.param("(MIT", id="unclosed-group"),
        pytest.param("MIT)", id="unmatched-closing-parenthesis"),
        pytest.param("AND MIT", id="leading-and"),
        pytest.param("OR MIT", id="leading-or"),
        pytest.param("WITH MIT", id="leading-with"),
        pytest.param("MIT AND", id="trailing-and"),
        pytest.param("MIT OR", id="trailing-or"),
        pytest.param("MIT WITH", id="trailing-with"),
        pytest.param("MIT AND OR Apache-2.0", id="consecutive-operators"),
        pytest.param("MIT AND ()", id="empty-right-operand"),
        pytest.param("(MIT OR)", id="operator-before-closing-parenthesis"),
        pytest.param(
            "MIT AND (OR Apache-2.0)", id="operator-after-opening-parenthesis"
        ),
    ],
)
def test_invalid_license_expression_syntax(license_expression: str) -> None:
    with pytest.raises(InvalidLicenseExpression) as exc_info:
        canonicalize_license_expression(license_expression)

    assert str(exc_info.value) == f"Invalid license expression: {license_expression!r}"


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
