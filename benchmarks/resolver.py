from __future__ import annotations

from packaging.specifiers import SpecifierSet
from packaging.version import Version

from . import add_attributes


class TimeResolverSuite:
    def setup(self) -> None:
        self.valid_versions = [
            "1.0.0",
            "1.0.0.post1",
            "1.0.1",
            "1.2.0",
            "1.2.5",
            "1.2.7",
            "1.3.0",
            "1.3.1",
            "2.0.0",
            "2.1.0",
            "2.1.1",
            "3.0.0",
        ]
        self.spec_strs = [
            ">=1.0.0,<2.0.0",
            ">=1.2.0,!=1.2.5,<3.0.0",
            ">=2.0.0,<3.0.0",
            ">=1.0.0,<=1.3.0",
            "==1.2.*",
            ">=1.0.0.post1,<2.0.0",
            ">=1.3.0,<2.0.0",
            ">=1.0.0,!=1.3.1,<3.0.0",
            ">=2.1.0,<3.0.0",
            "==1.0.0",
        ]

    @add_attributes(pretty_name="Resolver-style loop")
    def time_resolver_loop(self) -> None:
        versions = [Version(v) for v in self.valid_versions]
        specs = [SpecifierSet(s) for s in self.spec_strs]

        for spec in specs:
            candidates = [v for v in versions if v in spec]
            if candidates:
                max(candidates)
