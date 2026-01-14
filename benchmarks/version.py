from __future__ import annotations

from pathlib import Path

from packaging.version import InvalidVersion, Version

from . import add_attributes

DIR = Path(__file__).parent.resolve()


def valid_version(v: str) -> Version | None:
    try:
        return Version(v)
    except InvalidVersion:
        return None


VERSIONS_WITH_ZEROS = [
    "1.0.0.0.0",
    "3.1.0.0",
    "0.1.0.0.0",
    "1.0.0",
    "2.0.0",
    "1.2.0",
]


class TimeVersionSuite:
    def setup(self) -> None:
        with (DIR / "version_sample.txt").open() as f:
            self.versions = [v.strip() for v in f.readlines()]
        self.valid_versions = [ver for v in self.versions if (ver := valid_version(v))]

    @add_attributes(pretty_name="Version constructor")
    def time_constructor(self) -> None:
        for v in self.versions:
            try:
                Version(v)
            except InvalidVersion:  # noqa: PERF203
                pass

    @add_attributes(pretty_name="Version __str__")
    def time_str(self) -> None:
        for version in self.valid_versions:
            str(version)

    @add_attributes(pretty_name="Version sorting")
    def time_sort(self) -> None:
        sorted(self.valid_versions)

    @add_attributes(pretty_name="Stripping zeros")
    def time_zeros_key(self) -> None:
        ver = Version("2.0.0")
        for v in VERSIONS_WITH_ZEROS:
            Version(v) > ver  # noqa: B015
