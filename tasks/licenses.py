import json
import time

import httpx
import invoke

from .paths import SPDX_LICENSES

LATEST_API = "https://api.github.com/repos/spdx/license-list-data/releases/latest"
LICENSES_URL = (
    "https://raw.githubusercontent.com/spdx/license-list-data/v{}/json/licenses.json"
)
EXCEPTIONS_URL = (
    "https://raw.githubusercontent.com/spdx/license-list-data/v{}/json/exceptions.json"
)


def download_data(url):
    for _ in range(600):
        try:
            response = httpx.get(url)
            response.raise_for_status()
        except Exception:
            time.sleep(1)
            continue
        else:
            return json.loads(response.content.decode("utf-8"))

    message = "Download failed"
    raise ConnectionError(message)


@invoke.task
def update(ctx):
    print("Updating SPDX licenses...")

    latest_version = download_data(LATEST_API)["tag_name"][1:]
    print(f"Latest version: {latest_version}")

    license_payload = download_data(LICENSES_URL.format(latest_version))["licenses"]
    print(f"Licenses: {len(license_payload)}")

    exception_payload = download_data(EXCEPTIONS_URL.format(latest_version))[
        "exceptions"
    ]
    print(f"Exceptions: {len(exception_payload)}")

    licenses = []
    for license_data in license_payload:
        _l = {
            "spdx_license_key": license_data["licenseId"],
        }
        if license_data["isDeprecatedLicenseId"]:
            _l["is_deprecated"] = license_data["isDeprecatedLicenseId"]
        licenses.append(_l)

    for exception_data in exception_payload:
        _l = {
            "spdx_license_key": exception_data["licenseExceptionId"],
            "is_exception": True,
        }
        if exception_data["isDeprecatedLicenseId"]:
            _l["is_deprecated"] = exception_data["isDeprecatedLicenseId"]
        licenses.append(_l)

    with open(SPDX_LICENSES, "w", encoding="utf-8") as f:
        f.write(json.dumps(licenses))
