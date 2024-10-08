from packaging.licenses._spdx import EXCEPTIONS, LICENSES


def test_licenses():
    for license_id in LICENSES.keys():
        assert license_id == license_id.lower()


def test_exceptions():
    for exception_id in EXCEPTIONS.keys():
        assert exception_id == exception_id.lower()
