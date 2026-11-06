# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.

import pytest

from packaging.licenses import (
    InvalidLicenseExpression,
    canonicalize_license_expression,
)


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
    with pytest.raises(InvalidLicenseExpression):
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
