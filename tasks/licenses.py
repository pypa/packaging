import json
import time
from contextlib import closing
from io import StringIO

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
        except Exception:  # noqa: BLE001
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

    licenses = {}
    for license_data in license_payload:
        license_id = license_data["licenseId"]
        license_key = license_id.casefold()
        deprecated = license_data["isDeprecatedLicenseId"]
        licenses[license_key] = {"id": license_id, "deprecated": deprecated}

    exceptions = {}
    for exception_data in exception_payload:
        exception_id = exception_data["licenseExceptionId"]
        exception_key = exception_id.casefold()
        deprecated = exception_data["isDeprecatedLicenseId"]
        exceptions[exception_key] = {"id": exception_id, "deprecated": deprecated}

    with closing(StringIO()) as file_contents:
        file_contents.write(
            f"""\
from __future__ import annotations

VERSION = {latest_version!r}

# fmt: off
LICENSES: dict[str, dict[str, str | bool]] = {{
"""
        )

        for normalized_name, data in sorted(licenses.items()):
            file_contents.write(f"    {normalized_name!r}: {data!r},\n")

        file_contents.write("}\n\nEXCEPTIONS: dict[str, dict[str, str | bool]] = {\n")

        for normalized_name, data in sorted(exceptions.items()):
            file_contents.write(f"    {normalized_name!r}: {data!r},\n")

        file_contents.write("}\n# fmt: on\n")

        # Replace default Python single quotes with double quotes to adhere
        # to this project's desired formatting
        contents = file_contents.getvalue().replace("'", '"')

    with open(SPDX_LICENSES, "w", encoding="utf-8") as f:
        f.write(contents)
