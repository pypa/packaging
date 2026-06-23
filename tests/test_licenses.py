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
