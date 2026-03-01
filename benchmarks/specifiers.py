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
        self.specs = [SpecifierSet(s) for s in self.spec_strs]
        self.sample_versions = [Version(str(i / 10)) for i in range(1, 101)]

    @add_attributes(pretty_name="SpecifierSet constructor")
    def time_constructor(self) -> None:
        for s in self.spec_strs:
            SpecifierSet(s)

    @add_attributes(pretty_name="SpecifierSet contains")
    def time_contains(self) -> None:
        for spec in self.specs:
            spec.contains("3.12")

    @add_attributes(pretty_name="SpecifierSet filter")
    def time_filter_simple(self) -> None:
        list(SpecifierSet(">5.0").filter(self.sample_versions))

    @add_attributes(pretty_name="SpecifierSet filter")
    def time_filter_complex(self) -> None:
        list(SpecifierSet(">=1,~=1.1,!=1.2.1,==1.*,<1.9").filter(self.sample_versions))
