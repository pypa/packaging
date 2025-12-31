from __future__ import annotations

from pathlib import Path

from packaging.requirements import Requirement

from . import add_attributes

DIR = Path(__file__).parent.resolve()


class TimeRequirementSuite:
    def setup(self) -> None:
        with (DIR / "dist_sample.txt").open() as f:
            self.req_strs = [r.strip() for r in f]

    @add_attributes(pretty_name="Requirement constructor")
    def time_constructor(self) -> None:
        for r in self.req_strs:
            Requirement(r)
