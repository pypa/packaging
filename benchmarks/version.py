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


class TimeVersionSuite:
    def setup(self) -> None:
        with (DIR / "version_sample.txt").open() as f:
            self.versions = [v.strip() for v in f.readlines()]
        self.valid_versions = [v for v in self.versions if valid_version(v)]
        self.version_objects_cold = [Version(v) for v in self.valid_versions]
        self.version_objects_warm = [Version(v) for v in self.valid_versions]
        for v in self.version_objects_warm:
            _ = v._key

    @add_attributes(pretty_name="Version constructor")
    def time_constructor(self) -> None:
        for v in self.versions:
            try:
                Version(v)
            except InvalidVersion:  # noqa: PERF203
                pass

    @add_attributes(pretty_name="Version hash")
    def time_hash(self) -> None:
        for v in self.valid_versions:
            hash(Version(v))

    @add_attributes(pretty_name="Version __str__")
    def time_str(self) -> None:
        for version in self.valid_versions:
            str(Version(version))

    @add_attributes(pretty_name="Version sorting (cold cache)")
    def time_sort_cold(self) -> None:
        """Sorting when _key needs to be calculated during comparison."""
        for v in self.version_objects_cold:
            v._key_cache = None
        sorted(self.version_objects_cold)

    @add_attributes(pretty_name="Version sorting (warm cache)")
    def time_sort_warm(self) -> None:
        """Sorting when _key is already cached."""
        sorted(self.version_objects_warm)
