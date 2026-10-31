from __future__ import annotations

from pathlib import Path

# ASV also runs this benchmark against commits without prepare_environment.
import packaging.markers
from packaging.markers import Marker

from . import add_attributes

DIR = Path(__file__).parent.resolve()


class TimeMarkerSuite:
    rounds = 4

    def setup(self) -> None:
        with (DIR / "dist_sample.txt").open() as f:
            self.marker_strs = [m.split(";")[1].strip() for m in f if ";" in m]

        self.markers = [Marker(m) for m in self.marker_strs]
        # Measure repeated formatting and hashing after the first conversion.
        for marker in self.markers:
            str(marker)
        self.env = {
            "python_version": "3.12",
            "sys_platform": "linux",
            "platform_machine": "x86_64",
            "extra": "",
        }
        self.prepared_environment = (
            packaging.markers.prepare_environment(self.env)
            if hasattr(packaging.markers, "prepare_environment")
            else self.env
        )

    @add_attributes(pretty_name="Marker constructor")
    def time_constructor(self) -> None:
        for m in self.marker_strs:
            Marker(m)

    @add_attributes(pretty_name="Marker evaluate")
    def time_evaluate(self) -> None:
        for m in self.markers:
            m.evaluate(self.env)

    @add_attributes(pretty_name="Marker str")
    def time_str(self) -> None:
        for m in self.markers:
            str(m)

    @add_attributes(pretty_name="Marker hash")
    def time_hash(self) -> None:
        for m in self.markers:
            hash(m)

    @add_attributes(pretty_name="Marker constructor and first str")
    def time_first_str(self) -> None:
        for text in self.marker_strs:
            str(Marker(text))

    @add_attributes(pretty_name="Marker batch evaluate")
    def time_evaluate_many(self) -> None:
        if hasattr(packaging.markers, "prepare_environment"):
            for m in self.markers:
                m.evaluate_prepared(self.prepared_environment)
        else:
            for m in self.markers:
                m.evaluate(self.env)
