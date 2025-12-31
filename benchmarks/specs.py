from __future__ import annotations

from pathlib import Path

from packaging.specifiers import SpecifierSet

DIR = Path(__file__).parent.resolve()


class TimeSpecParsingSuite:
    def setup(self) -> None:
        with (DIR / "specs_sample.txt").open() as f:
            self.specs = [s.strip() for s in f.readlines()]

    def time_constructor(self) -> None:
        for s in self.specs:
            SpecifierSet(s)


class TimeSpecSuite:
    def setup(self) -> None:
        with (DIR / "specs_sample.txt").open() as f:
            self.specs = [SpecifierSet(s.strip()) for s in f.readlines()]

    def time_contains(self) -> None:
        for spec in self.specs:
            spec.contains("3.12")
