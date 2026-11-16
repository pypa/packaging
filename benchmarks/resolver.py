from __future__ import annotations

from typing import TYPE_CHECKING

from packaging.specifiers import SpecifierSet
from packaging.version import Version

from . import add_attributes
from ._pubgrub import Solver

if TYPE_CHECKING:
    from ._pubgrub import Catalogue


class TimeResolverSuite:
    rounds = 4

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


class TimePubGrubSuite:
    """
    Run one solve that must recover from several bad choices.

    The roots require app >=1 and target ==2. Arrows mean "depends on".
    Only app 2 requires left, right and middle:

        app 2 --> left 1  --> shared >=1 --+
              --> right 1 --> shared <2 ---+--> shared 1 --> target ==1
              --> middle 1
        root --------------------------------------------> target ==2

    The package shared has versions 1 and 2. The two incoming constraints force
    version 1, whose target ==1 requirement conflicts with the root's target ==2.
    The release app 1 has no left, right or middle dependency. The package middle
    has no dependencies and cannot fix the conflict; it exercises jumps past
    unrelated choices.

    Both app releases also require these packages:

        app 1 or 2 --+--> cycle-a 1 <--> cycle-b 1
                     +--> local ==1
                     +--> self >=1
                     +--> steady 1 --> target ==2

    The common dependencies add two more failed choices:

        package   first choice   why it fails          selected
        -------   ------------   -------------------   --------
        local     1+2            needs missing >=1      1+1
        self      2              needs self <2          1

    The local requirement ==1 admits both local versions; decisions use exact
    points, as described in Solver.decide(). The release self 1 requires self ==1,
    which is already satisfied. Once both cycle versions are selected, their
    requirements also hold.

    Final pins:

        app=1   cycle-a=1   cycle-b=1   local=1+1
        self=1  steady=1    target=2

    Setup stores the scenario as strings. The timer builds fresh version and
    range objects, then creates and runs one Solver. Preparation and the complete
    search are timed together, including sorting and failed branches, as in
    TimeResolverSuite.
    Reference partial-satisfier example:
    https://github.com/dart-lang/pub/blob/master/doc/solver.md#conflict-resolution-with-a-partial-satisfier
    """

    rounds = 4

    def setup(self) -> None:
        common = {
            "cycle-a": "==1",
            "local": "==1",
            "self": ">=1",
            "steady": "==1",
        }

        self.releases: dict[str, dict[str, dict[str, str]]] = {
            "app": {
                "1": common,
                "2": {
                    **common,
                    "left": ">=1",
                    "right": ">=1",
                    "middle": ">=1",
                },
            },
            "cycle-a": {"1": {"cycle-b": "==1"}},
            "cycle-b": {"1": {"cycle-a": "==1"}},
            "left": {"1": {"shared": ">=1"}},
            "local": {
                "1": {},
                "1+1": {},
                "1+2": {"missing": ">=1"},
            },
            "middle": {"1": {}},
            "right": {"1": {"shared": "<2"}},
            "self": {"1": {"self": "==1"}, "2": {"self": "<2"}},
            "shared": {"1": {"target": "==1"}, "2": {}},
            "steady": {"1": {"target": "==2"}},
            "target": {"1": {}, "2": {}},
        }
        self.requirements = {"app": ">=1", "target": "==2"}

    @add_attributes(pretty_name="PubGrub resolver loop")
    def time_resolver_loop(self) -> None:
        # Time object construction as well as search.
        catalogue: Catalogue = {}

        for package, releases in self.releases.items():
            catalogue[package] = {}
            for version, dependencies in releases.items():
                catalogue[package][Version(version)] = {
                    name: SpecifierSet(spec, prereleases=True).to_range()
                    for name, spec in dependencies.items()
                }

        requirements = {
            name: SpecifierSet(spec, prereleases=True).to_range()
            for name, spec in self.requirements.items()
        }

        Solver(catalogue, requirements).solve()
