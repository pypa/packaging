from packaging.licenses._spdx import EXCEPTIONS, LICENSES


def test_licenses():
    for license_id in LICENSES:
        assert license_id == license_id.lower()


def test_exceptions():
    for exception_id in EXCEPTIONS:
        assert exception_id == exception_id.lower()
