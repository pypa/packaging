from __future__ import annotations

import pathlib
from contextlib import closing
from io import StringIO
from textwrap import dedent
from typing import Any

import httpx

LATEST_SPDX_GITHUB_RELEASE_URL = (
    "https://api.github.com/repos/spdx/license-list-data/releases/latest"
)
LICENSES_URL = (
    "https://raw.githubusercontent.com/spdx/license-list-data/v{}/json/licenses.json"
)
EXCEPTIONS_URL = (
    "https://raw.githubusercontent.com/spdx/license-list-data/v{}/json/exceptions.json"
)


def download_data(url: str) -> Any:  # noqa: ANN401
    transport = httpx.HTTPTransport(retries=3)
    client = httpx.Client(transport=transport)

    response = client.get(url)
    response.raise_for_status()
    return response.json()


def main() -> None:
    latest_version = download_data(LATEST_SPDX_GITHUB_RELEASE_URL)["tag_name"][1:]

    licenses = {}
    for license_data in download_data(LICENSES_URL.format(latest_version))["licenses"]:
        license_id = license_data["licenseId"]
        deprecated = license_data["isDeprecatedLicenseId"]
        licenses[license_id.lower()] = {"id": license_id, "deprecated": deprecated}

    exceptions = {}
    for exception_data in download_data(EXCEPTIONS_URL.format(latest_version))[
        "exceptions"
    ]:
        exception_id = exception_data["licenseExceptionId"]
        deprecated = exception_data["isDeprecatedLicenseId"]
        exceptions[exception_id.lower()] = {
            "id": exception_id,
            "deprecated": deprecated,
        }

    project_root = pathlib.Path(__file__).resolve().parent.parent
    data_file = project_root / "src" / "packaging" / "licenses" / "_spdx.py"

    with closing(StringIO()) as file_contents:
        file_contents.write(
            dedent(
                f"""
                from __future__ import annotations

                from typing import TypedDict

                class SPDXLicense(TypedDict):
                    id: str
                    deprecated: bool

                class SPDXException(TypedDict):
                    id: str
                    deprecated: bool


                VERSION = {latest_version!r}

                LICENSES: dict[str, SPDXLicense] = {{
                """
            )
        )

        for normalized_name, data in sorted(licenses.items()):
            file_contents.write(f"    {normalized_name!r}: {data!r},\n")

        file_contents.write("}\n\nEXCEPTIONS: dict[str, SPDXException] = {\n")

        for normalized_name, data in sorted(exceptions.items()):
            file_contents.write(f"    {normalized_name!r}: {data!r},\n")

        file_contents.write("}\n")

        with data_file.open("w", encoding="utf-8") as f:
            f.write(file_contents.getvalue())


if __name__ == "__main__":
    main()
