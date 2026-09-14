# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.

import pytest

from packaging.licenses import canonicalize_license_expression


@pytest.mark.parametrize(
    ("license_expression", "expected"),
    [
        # SPDX LicenseRef- identifiers are case-sensitive, so two refs that
        # differ only in case are distinct and must each keep their spelling.
        ("LicenseRef-mit OR licenseref-MIT", "LicenseRef-mit OR LicenseRef-MIT"),
        ("licenseref-MIT AND LicenseRef-mit", "LicenseRef-MIT AND LicenseRef-mit"),
        ("LICENSEREF-Foo AND licenseref-foo", "LicenseRef-Foo AND LicenseRef-foo"),
        # A single ref still round-trips its own spelling.
        ("licenseref-public-domain", "LicenseRef-public-domain"),
        # Refs mixed with other tokens keep their per-occurrence spelling.
        (
            "(LicenseRef-Foo OR licenseref-foo) AND MIT",
            "(LicenseRef-Foo OR LicenseRef-foo) AND MIT",
        ),
    ],
)
def test_licenseref_spelling_preserved_per_occurrence(
    license_expression: str, expected: str
) -> None:
    assert canonicalize_license_expression(license_expression) == expected
