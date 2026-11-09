# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from packaging.ranges import VersionRange
from packaging.specifiers import SpecifierSet

from .version import valid_version

if TYPE_CHECKING:
    from packaging.version import Version

DIR = Path(__file__).parent.resolve()


class TimeRangeFilter:
    rounds = 4
    params = (("full", "bounded", "admit", "reject"), ("versions", "strings"))
    param_names = ("range", "input")

    def setup(self, range_name: str, input_type: str) -> None:
        with (DIR / "version_sample.txt").open() as f:
            versions = [
                v for line in f if (v := valid_version(line.strip())) is not None
            ]

        literal = SpecifierSet("===1.0").to_range()
        self.range = {
            "full": VersionRange.full(),
            "bounded": SpecifierSet(">=1,<3").to_range(),
            "admit": literal,
            "reject": VersionRange.full() - literal,
        }[range_name]
        self.items: list[Version] | list[str] = (
            versions if input_type == "versions" else [str(v) for v in versions]
        )

    def time_filter(self, _range_name: str, _input_type: str) -> None:
        list(self.range.filter(self.items))
