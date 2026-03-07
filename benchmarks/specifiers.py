from __future__ import annotations

from pathlib import Path

from packaging.specifiers import SpecifierSet
from packaging.version import Version

from . import add_attributes

DIR = Path(__file__).parent.resolve()


class TimeSpecSuite:
    def setup(self) -> None:
        with (DIR / "specs_sample.txt").open() as f:
            self.spec_strs = [s.strip() for s in f.readlines()]

        # Build and warm versions
        self.single_version = Version("3.12")
        self.sample_versions = [Version(str(i / 10)) for i in range(1, 11)]
        self.single_version._key  # noqa: B018
        for v in self.sample_versions:
            v._key  # noqa: B018

        # Build cold specifiers
        self._single_cold_spec = SpecifierSet(">0.5")
        self._cold_specs = [SpecifierSet(s) for s in self.spec_strs]

        # Build warm specifiers
        self._single_warm_spec = SpecifierSet(">0.5")
        self._warm_specs = [SpecifierSet(s) for s in self.spec_strs]
        for s in self._warm_specs:
            for sp in s._specs:
                sp.contains(self.single_version)
        for sp in self._single_warm_spec._specs:
            sp.contains(self.single_version)

    @add_attributes(pretty_name="SpecifierSet constructor")
    def time_constructor(self) -> None:
        for s in self.spec_strs:
            SpecifierSet(s)

    @add_attributes(pretty_name="SpecifierSet contains (cold)")
    def time_contains_cold(self) -> None:
        for spec in self._cold_specs:
            for sp in spec._specs:
                sp._spec_version = None

        for spec in self._cold_specs:
            spec.contains(self.single_version)

    @add_attributes(pretty_name="SpecifierSet contains (warm)")
    def time_contains_warm(self) -> None:
        for spec in self._warm_specs:
            spec.contains(self.single_version)

    @add_attributes(pretty_name="SpecifierSet filter (simple, cold)")
    def time_filter_simple_cold(self) -> None:
        for sp in self._single_cold_spec._specs:
            sp._spec_version = None
        list(self._single_cold_spec.filter(self.sample_versions))

    @add_attributes(pretty_name="SpecifierSet filter (simple, warm)")
    def time_filter_simple_warm(self) -> None:
        list(self._single_warm_spec.filter(self.sample_versions))
