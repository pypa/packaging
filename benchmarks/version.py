from __future__ import annotations

from pathlib import Path

from packaging.version import InvalidVersion, Version

DIR = Path(__file__).parent.resolve()


class TimeVersionParsingSuite:
    def setup(self) -> None:
        with (DIR / "version_sample.txt").open() as f:
            self.versions = [v.strip() for v in f.readlines()]

    def time_constructor(self) -> None:
        for v in self.versions:
            try:
                Version(v)
            except InvalidVersion:  # noqa: PERF203
                pass


def valid_version(v: str) -> Version | None:
    try:
        return Version(v)
    except InvalidVersion:
        return None


class TimeVersionSuite:
    def setup(self) -> None:
        with (DIR / "version_sample.txt").open() as f:
            self.versions = [
                ver for v in f.readlines() if (ver := valid_version(v.strip()))
            ]

    def time_str(self) -> None:
        for version in self.versions:
            str(version)
