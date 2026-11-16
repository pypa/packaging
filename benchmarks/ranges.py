# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.
from __future__ import annotations

from pathlib import Path

from packaging.ranges import VersionRange
from packaging.specifiers import SpecifierSet
from packaging.version import Version

from . import add_attributes

DIR = Path(__file__).parent.resolve()


class TimeRangeSuite:
    rounds = 4

    # Protobuf requirements from googleapis-common-protos 1.52.0 and BigQuery 3.4.0.
    SIMPLE_SPEC = ">=3.6.0"
    COMPLEX_SPEC = (
        ">=3.19.5,<5.0.0dev,!=3.20.0,!=3.20.1,"
        "!=4.21.0,!=4.21.1,!=4.21.2,!=4.21.3,!=4.21.4,!=4.21.5"
    )

    def setup(self) -> None:
        with (DIR / "specs_sample.txt").open() as f:
            spec_strs = [s.strip() for s in f]

        self._cold_specs = [SpecifierSet(s, prereleases=True) for s in spec_strs]
        self._warm_specs = [SpecifierSet(s, prereleases=True) for s in spec_strs]
        self.ranges = [spec.to_range() for spec in self._warm_specs]

        # Set operations require operands with the same prerelease policy.
        self.simple_range = SpecifierSet(self.SIMPLE_SPEC, prereleases=True).to_range()
        self.complex_range = SpecifierSet(
            self.COMPLEX_SPEC, prereleases=True
        ).to_range()
        self.single_version = Version("3.12")

        # Published protobuf releases below, within and above the requirement bounds.
        self.versions = [
            Version(v)
            for v in (
                "3.0.0",
                "3.6.0",
                "3.19.4",
                "3.19.5",
                "3.20.0rc1",
                "3.20.0",
                "3.20.1",
                "3.20.2",
                "4.21.0rc1",
                "4.21.0rc2",
                "4.21.0",
                "4.21.1",
                "4.21.2",
                "4.21.3",
                "4.21.4",
                "4.21.5",
                "4.21.6",
                "4.22.0",
                "5.26.0",
            )
        ]

        self.default_range = SpecifierSet(self.SIMPLE_SPEC).to_range()
        self.prerelease_versions = [Version("4.21.0rc1"), Version("4.21.0rc2")]
        # Buffer prereleases before encountering a final that suppresses them.
        self.default_versions = [*self.prerelease_versions, Version("4.21.0")]

    @add_attributes(pretty_name="VersionRange from SpecifierSet (cold)", number=1)
    def time_constructor_cold(self) -> None:
        for spec in self._cold_specs:
            spec.to_range()

    @add_attributes(pretty_name="VersionRange from SpecifierSet (warm)")
    def time_constructor_warm(self) -> None:
        for spec in self._warm_specs:
            spec.to_range()

    @add_attributes(pretty_name="VersionRange singleton")
    def time_singleton(self) -> None:
        for version in self.versions:
            VersionRange.singleton(version, prereleases=True)

    @add_attributes(pretty_name="VersionRange contains")
    def time_contains(self) -> None:
        for constraint in self.ranges:
            constraint.contains(self.single_version)

    @add_attributes(pretty_name="VersionRange filter (simple)")
    def time_filter_simple(self) -> None:
        list(self.simple_range.filter(self.versions))

    @add_attributes(pretty_name="VersionRange filter (complex)")
    def time_filter_complex(self) -> None:
        list(self.complex_range.filter(self.versions))

    @add_attributes(pretty_name="VersionRange filter (default prereleases)")
    def time_filter_default(self) -> None:
        list(self.default_range.filter(self.default_versions))

    @add_attributes(pretty_name="VersionRange filter (prerelease fallback)")
    def time_filter_prerelease_fallback(self) -> None:
        list(self.default_range.filter(self.prerelease_versions))

    @add_attributes(pretty_name="VersionRange intersection")
    def time_intersection(self) -> None:
        for constraint in self.ranges:
            constraint.intersection(self.complex_range)

    @add_attributes(pretty_name="VersionRange union")
    def time_union(self) -> None:
        for constraint in self.ranges:
            constraint.union(self.complex_range)

    @add_attributes(pretty_name="VersionRange difference")
    def time_difference(self) -> None:
        for constraint in self.ranges:
            constraint.difference(self.complex_range)

    @add_attributes(pretty_name="VersionRange complement")
    def time_complement(self) -> None:
        for constraint in self.ranges:
            constraint.complement()

    @add_attributes(pretty_name="VersionRange is_subset")
    def time_is_subset(self) -> None:
        for constraint in self.ranges:
            constraint.is_subset(self.complex_range)

    @add_attributes(pretty_name="VersionRange is_disjoint")
    def time_is_disjoint(self) -> None:
        for constraint in self.ranges:
            constraint.is_disjoint(self.complex_range)

    @add_attributes(pretty_name="VersionRange relation")
    def time_relation(self) -> None:
        for constraint in self.ranges:
            constraint.relation(self.complex_range)
