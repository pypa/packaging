from __future__ import annotations

from packaging.utils import canonicalize_name

from . import add_attributes

NAMES = [
    "simple",
    "verysimple",
    "moresimple",
    "other",
    "numpy",
    "packaging",
    "requests",
    "a",
    "long_name_with_multiple_parts",
    "snake-name",
    "another-snake-name",
    "name-with-dashes-and_underscores",
    "NAMEWITHUPPERCASELETTERS",
    "name.with.dots.in.it",
    "name--with..multiple---separators__in..a..row",
    "CamelName",
]

class TimeUtils:
    @add_attributes(pretty_name="canonicalize_name")
    def time_canonicalize_name(self) -> None:
        for v in NAMES:
            canonicalize_name(v)
