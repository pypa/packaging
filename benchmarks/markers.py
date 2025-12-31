from __future__ import annotations

from pathlib import Path

from packaging.markers import Marker

from . import add_attributes

DIR = Path(__file__).parent.resolve()

class TimeMarkerSuite:
    def setup(self) -> None:
        with (DIR / "dist_sample.txt").open() as f:
            self.marker_strs = [m.split(";")[1].strip() for m in f if ";" in m]

        self.markers = [Marker(m) for m in self.marker_strs]
        self.env = {
            "python_version": "3.12",
            "sys_platform": "linux",
            "platform_machine": "x86_64",
            "extra": "",
        }

    @add_attributes(pretty_name="Marker constructor")
    def time_constructor(self) -> None:
        for m in self.marker_strs:
            Marker(m)

    @add_attributes(pretty_name="Marker evaluate")
    def time_evaluate(self) -> None:
        for m in self.markers:
            m.evaluate(self.env)
