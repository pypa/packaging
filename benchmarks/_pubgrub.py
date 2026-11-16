# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.
"""
A PubGrub walkthrough used by the resolver macrobenchmark.

Run ``asv run --bench pubgrub.TimePubGrubSuite``. The input catalogue lists
all available versions and their dependencies. Solver.solve() returns pins:
one chosen version for each required package.

A term describes one package, such as "library >=1". An incompatibility lists
terms that cannot all be true. Dependencies become forbidden pairs:

    dependency:   app 2 requires library >=1
    forbidden:    app is 2 AND NOT(library >=1)
    deduction:    app is 2  ==>  library >=1 and present

In Boolean satisfiability (SAT), a clause is an OR: one true condition is
enough. An incompatibility is an AND that must be false: one false condition
is enough to avoid the conflict.

References:

* Introduction: https://nex3.medium.com/pubgrub-2fb6470504f
* Algorithm: https://github.com/dart-lang/pub/blob/master/doc/solver.md
* Terms and resolution: https://pubgrub-rs-guide.pages.dev/internals/incompatibilities
* Boolean background: https://en.wikipedia.org/wiki/Conflict-driven_clause_learning
* Reference implementation:
  https://github.com/dart-lang/pub/blob/master/lib/src/solver/version_solver.dart

This prototype uses PEP 440 versions with prereleases explicitly admitted.
Root requirements are fixed before any choices, at level zero. There is no
separate root package version. It scans all incompatibilities and rebuilds
state after a backjump, which undoes later choices and deductions. Dependency
facts describe single versions, without combining adjacent releases. It chooses
a candidate before propagating its dependencies; Dart can reject that choice
first when a dependency already conflicts. Markers, extras, prerelease fallback
and human-readable failure explanations are omitted.
"""

from __future__ import annotations

from dataclasses import dataclass

from packaging.ranges import VersionRange
from packaging.version import Version

FULL = VersionRange.full(admit_arbitrary=False, prereleases=True)


@dataclass(slots=True)
class Domain:
    """
    Store the values a package term allows: versions and possible absence.

    The absence bit means "not installing this package is still allowed".
    Excluding a version does not itself require the package to be installed.

        term                 allowed versions    absent
        -------------------  ------------------  ------
        package >=2          >=2                 False
        NOT(package >=2)     below 2             True
        selected package 2   exactly 2           False
        unconstrained        all versions        True

    Intersection keeps values allowed by both terms; union keeps values allowed
    by either. Inverse allows what the original term rules out, including flipping
    the absence bit. Local versions have a + suffix, such as 2+local. The exact
    point {2} does not include that variant. All ranges use prereleases=True for
    these set operations.
    """

    versions: VersionRange
    absent: bool = False

    def intersection(self, other: Domain) -> Domain:
        return Domain(self.versions & other.versions, self.absent and other.absent)

    def union(self, other: Domain) -> Domain:
        return Domain(self.versions | other.versions, self.absent or other.absent)

    def inverse(self) -> Domain:
        return Domain(FULL - self.versions, not self.absent)

    def is_empty(self) -> bool:
        return not self.absent and self.versions.is_empty

    def is_full(self) -> bool:
        return self.absent and FULL.is_subset(self.versions)

    def is_subset(self, other: Domain) -> bool:
        return (not self.absent or other.absent) and self.versions.is_subset(
            other.versions
        )

    def is_disjoint(self, other: Domain) -> bool:
        return not (self.absent and other.absent) and self.versions.is_disjoint(
            other.versions
        )


UNCONSTRAINED = Domain(FULL, absent=True)
# Each package occurs once; intersect repeated terms for that package.
Incompatibility = dict[str, Domain]
Dependencies = dict[str, VersionRange]
Catalogue = dict[str, dict[Version, Dependencies]]


@dataclass(slots=True)
class Assignment:
    """
    Store one chosen version or one deduction, in the order it was made.

    A decision chooses a version. A derivation records a constraint forced by
    known incompatibilities. The trail is an ordered list of both. Each entry
    records the current decision level: the number of choices retained so far.

        level  assignment         cause
        -----  -----------------  ---------------------
          0    root requirements  root incompatibility
          1    choose app 2       None (a decision)
          1    library >=1        app's dependency
          2    choose library 2   None (a decision)

    A backjump undoes later choices and deductions. Their incompatibilities remain
    available to prevent the same conflict.
    https://pubgrub-rs-guide.pages.dev/internals/partial_solution
    """

    package: str
    domain: Domain
    level: int
    cause: Incompatibility | None


class ResolutionError(Exception):
    """
    No selection of catalogue versions satisfies the root requirements.
    """


def resolve_incompatibilities(
    conflict: Incompatibility, cause: Incompatibility, pivot: str
) -> Incompatibility:
    """
    Combine a conflict with the reason for its latest assignment.

    The pivot is the package whose assignment we are explaining. T and C are
    its two allowed-value sets; A and B stand for the other conditions.

        conflict:  (pivot in T) AND A
        cause:     (pivot in C) AND B
        ---------------------------------------
        result:    (pivot in (T | C)) AND A AND B

    The pivot allows values from either T or C. Shared packages in A and B must
    satisfy both conditions, so their value sets intersect. If T | C includes every
    version and absence, that condition is always true and can be dropped. Keep
    a smaller union: earlier assignments may be needed to show why the pivot's
    term holds.
    https://pubgrub-rs-guide.pages.dev/internals/incompatibilities#rule-of-resolution
    """
    resolved = dict(conflict)

    for package, term in cause.items():
        if package == pivot:
            resolved[package] = resolved[package].union(term)
        else:
            resolved[package] = resolved.get(package, UNCONSTRAINED).intersection(term)

    # An always-true term adds nothing to a forbidden conjunction.
    if resolved[pivot].is_full():
        del resolved[pivot]

    return resolved


class Solver:
    """
    Choose compatible releases from a complete, fixed catalogue.

    Every root and dependency range must use prereleases=True. All releases
    must be PEP 440 versions; arbitrary version strings are not supported.

        attribute   contents
        ----------  ---------------------------------------------------
        domains     values still allowed for each package
        trail       choices and deductions, in the order they were made
        decisions   selected releases; the result when search finishes

    After a backjump, rebuild domains and decisions from the remaining trail.
    Choose package names alphabetically and releases from newest to oldest.
    """

    def __init__(self, catalogue: Catalogue, roots: Dependencies) -> None:
        self.catalogue = catalogue
        self.versions = {
            package: sorted(releases, reverse=True)
            for package, releases in catalogue.items()
        }

        # Forbid each root requirement's inverse, including package absence.
        self.incompatibilities = [
            {package: Domain(constraint).inverse()}
            for package, constraint in roots.items()
        ]

        self.domains: dict[str, Domain] = {}
        self.trail: list[Assignment] = []
        self.decisions: dict[str, Version] = {}
        self.expanded: set[tuple[str, Version]] = set()
        self.level = 0

    def solve(self) -> dict[str, Version]:
        """
        Apply forced constraints, resolve conflicts, then make another choice.

        When a package has no release in its allowed range, record that the range
        is unavailable. This fact will force a conflict during propagation.

        learn() follows the assignments that force the conflict. L is their
        latest decision level, or zero when no assignment is needed. Several
        deductions can share a level, so earlier in the trail does not always
        mean a lower decision level.

            START
              |
              v
            (A) propagate
              |
              +-- conflict --> learn: (B) find support and L
              |                 |
              |                 +-- L == 0 --> [FAILURE]
              |                 |              raise ResolutionError
              |                 |
              |                 +-- L > 0 --> were the other constraints
              |                                 established below L?
              |                                 |
              |                                 +-- yes --> keep reason; backjump
              |                                 |              |
              |                                 |              +--> repeat (A)
              |                                 |
              |                                 +-- no --> resolve with its cause
              |                                              |
              |                                              +--> repeat (B)
              |
              +-- no conflict --> all required packages chosen?
                                    |
                                    +-- yes --> [SUCCESS]
                                    |           return pins
                                    |
                                    +-- no --> decide --> repeat (A)

        At level zero the conflict follows from fixed requirements and package
        facts. No choice can be undone to repair it, so the solve fails.

        The other constraints are the assignments needed to keep the conflict's
        remaining terms true, plus any earlier support for the latest term's own
        package. For example:

            other constraints   latest assignment   action
            -----------------   -----------------   ------------------------
            at levels 0 and 2   at level 5          backjump to 2
            also need level 5   at level 5          resolve its cause first

        If those constraints are all below L, a backjump can keep them and undo
        the latest assignment. The retained incompatibility then forces its
        remaining term false. A version choice always qualifies: it is the first
        assignment at its level. Otherwise, combine the latest deduction with its
        cause to find an earlier explanation, then repeat (B).

        previous_satisfier_level() accounts for the same-package support.
        SUCCESS and FAILURE end the solve. (A) repeats propagation; (B) repeats
        conflict analysis inside learn().

        A package needs a chosen version only when its domain rules out absence.
        https://github.com/dart-lang/pub/blob/master/doc/solver.md#the-algorithm
        """
        while True:
            conflict = self.propagate()
            if conflict is not None:
                self.learn(conflict)
                continue

            # Negative constraints alone do not require selecting a package.
            package = min(
                (
                    package
                    for package, domain in self.domains.items()
                    if not domain.absent and package not in self.decisions
                ),
                default=None,
            )
            if package is None:
                return dict(self.decisions)

            self.decide(package)

    def propagate(self) -> Incompatibility | None:
        """
        Apply forced constraints until a scan makes no changes, or find a conflict.

        For a term T and current allowed values S, the term is true if every value
        in S is also in T. It is false if they share no values. Otherwise it can
        still be true or false: it is undetermined.

            terms known false   terms undetermined   result
            -----------------   ------------------   --------------------------
            one or more         any                  skip this incompatibility
            none                none                 conflict: all terms hold
            none                one                  rule out that term
            none                two or more          no deduction yet

        With one undetermined term and all others true, the incompatibility is
        almost satisfied. Force that last term false to avoid the forbidden
        combination. This is unit propagation. Repeat the scan because a new
        deduction can make an earlier incompatibility almost satisfied.
        https://github.com/dart-lang/pub/blob/master/doc/solver.md#unit-propagation
        """
        changed = True

        while changed:
            changed = False

            for incompatibility in self.incompatibilities:
                undetermined: str | None = None

                for package, term in incompatibility.items():
                    current = self.domains.get(package, UNCONSTRAINED)
                    if current.is_disjoint(term):
                        break

                    if not current.is_subset(term):
                        # Two undetermined terms leave no forced deduction.
                        if undetermined is not None:
                            break

                        undetermined = package
                else:
                    # No term is false, and at most one is undetermined.
                    if undetermined is None:
                        return incompatibility

                    # All other terms hold, so this one must be false.
                    self.assign(
                        undetermined,
                        incompatibility[undetermined].inverse(),
                        incompatibility,
                    )
                    changed = True

        return None

    def learn(self, incompatibility: Incompatibility) -> None:
        """
        Find why the choices conflict, then undo enough choices to continue.

        A term's satisfier is the assignment that first makes it true, together
        with earlier assignments. The latest such assignment is where all the
        conflict's terms first hold.

            latest satisfier
                    |
            was it a version choice, or were the other
            constraints recorded at lower levels?
                    | yes                         | no
                    v                             v
            backjump to earlier level     combine with its cause
                    |                             |
            propagate again               inspect the new conflict

        previous_satisfier_level() finds how far back to jump. It must account for
        earlier assignments for the same package, as well as the other terms.
        A level-zero conflict cannot be repaired by undoing choices, so it proves
        failure. Keep newly derived incompatibilities; the original is already known.
        https://github.com/dart-lang/pub/blob/master/doc/solver.md#conflict-resolution
        """
        learned = False

        while True:
            satisfiers = self.satisfiers(incompatibility)
            if not satisfiers:
                raise ResolutionError

            _, latest = satisfiers[-1]
            if latest.level == 0:
                raise ResolutionError

            previous_level = self.previous_satisfier_level(incompatibility, satisfiers)

            if latest.cause is None or previous_level < latest.level:
                if learned:
                    self.incompatibilities.append(incompatibility)

                # The jump leaves one term undetermined and the rest true.
                self.backtrack(previous_level)
                return

            # Replace the latest deduction with the conditions that forced it.
            incompatibility = resolve_incompatibilities(
                incompatibility, latest.cause, latest.package
            )
            learned = True

    def decide(self, package: str) -> None:
        """
        Choose a release and record its dependency requirements.

        First look for a release in the package's current allowed range. If there
        is none, record that the range is unavailable. This remains true after a
        backjump because the catalogue is fixed.

        For a chosen parent version v and its dependency range R:

            requirement:   parent v needs child in R
            forbidden:     parent is v AND child is NOT in R

        The negative child term includes not installing the child. If parent and
        child are the same package, intersect their two conditions. Use exact points
        for decisions: {1+1} excludes 1+2, while the PEP 440 specifier ==1 admits both.
        https://github.com/dart-lang/pub/blob/master/doc/solver.md#decision-making
        """
        domain = self.domains[package]
        version = next(
            (
                version
                for version in self.versions.get(package, [])
                if version in domain.versions
            ),
            None,
        )

        if version is None:
            # The fixed catalogue makes this unavailable range a permanent fact.
            self.incompatibilities.append({package: Domain(domain.versions)})
            return

        # A decision needs an exact point; ==1 would also admit local versions.
        singleton = Domain(VersionRange.singleton(version, prereleases=True))

        # Dependency facts stay valid after backtracking; add them only once.
        if (package, version) not in self.expanded:
            for dependency, constraint in self.catalogue[package][version].items():
                negative = Domain(constraint).inverse()

                if dependency == package:
                    # Both conditions must hold for the same package version.
                    term = singleton.intersection(negative)
                    if term.is_empty():
                        continue

                    incompatibility = {package: term}
                else:
                    incompatibility = {package: singleton, dependency: negative}

                self.incompatibilities.append(incompatibility)

            self.expanded.add((package, version))

        # Deductions from this choice inherit its new decision level.
        self.level += 1
        self.decisions[package] = version
        self.assign(package, singleton, None)

    def assign(
        self, package: str, domain: Domain, cause: Incompatibility | None
    ) -> None:
        """
        Record a choice or deduction and narrow the package's allowed values.
        """
        current = self.domains.get(package, UNCONSTRAINED)
        narrowed = current.intersection(domain)

        # Propagation only forces undetermined terms; choices use allowed versions.
        assert not narrowed.is_empty()
        self.domains[package] = narrowed

        self.trail.append(Assignment(package, domain, self.level, cause))

    def satisfiers(
        self, incompatibility: Incompatibility
    ) -> list[tuple[int, Assignment]]:
        """
        Find the assignment that first forces each term to be true.

        Replay the trail from oldest to newest. The assignments read so far form
        a prefix of the trail. Their combined constraints can force a term that
        no single assignment forces alone:

            assignment read   allowed values so far
            ----------------  -------------------------------------
            shared >=1        >=1
            shared <2         >=1,<2  (now forces the term >=1,<2)

        Return (trail index, assignment) pairs in trail order. The last pair marks
        where all terms first hold. Terms allowing every version and absence already
        hold before the trail starts; they need no assignment.
        """
        domains: dict[str, Domain] = {}
        found: dict[str, tuple[int, Assignment]] = {}

        for index, assignment in enumerate(self.trail):
            package = assignment.package
            current = domains.get(package, UNCONSTRAINED)
            domains[package] = current.intersection(assignment.domain)

            # Terms true before the trail starts need no supporting assignment.
            if (
                package in incompatibility
                and package not in found
                and not incompatibility[package].is_full()
                and domains[package].is_subset(incompatibility[package])
            ):
                found[package] = (index, assignment)

        # Dictionary insertion order keeps the satisfiers in trail order.
        return list(found.values())

    def previous_satisfier_level(
        self,
        incompatibility: Incompatibility,
        satisfiers: list[tuple[int, Assignment]],
    ) -> int:
        """
        Find the last earlier level needed alongside the latest assignment.

            earlier constraint:  shared >=1       level 2
            latest assignment:   shared <2        level 3
            conflicting term:    shared >=1,<2
            residual:            shared <1

        The residual contains values the latest assignment allows but the term
        rules out. An earlier constraint must have excluded those values. Here,
        shared >=1 excludes the residual, so at least level 2 must remain for this
        term. Include that level alongside the satisfier levels of the other terms.
        https://github.com/dart-lang/pub/blob/master/doc/solver.md#conflict-resolution-with-a-partial-satisfier
        """
        index, latest = satisfiers[-1]
        previous_level = max((entry.level for _, entry in satisfiers[:-1]), default=0)

        # Earlier assignments may supply the part the latest one does not.
        residual = latest.domain.intersection(incompatibility[latest.package].inverse())
        if not residual.is_empty():
            prefix = UNCONSTRAINED

            # Other packages are accounted for above; replay this one's support.
            for entry in self.trail[:index]:
                if entry.package == latest.package:
                    prefix = prefix.intersection(entry.domain)

                    if prefix.is_disjoint(residual):
                        previous_level = max(previous_level, entry.level)
                        break

        return previous_level

    def backtrack(self, level: int) -> None:
        """
        Undo later choices and rebuild the allowed-value and selected-version maps.

            levels before:  0  1  2  3  4
            jump to 1:      0  1

        Keep all known incompatibilities, including learned ones. Dependencies required
        only by discarded choices become optional again.
        """
        self.trail = [entry for entry in self.trail if entry.level <= level]

        # Keep the exact versions of decisions that survived the jump.
        self.decisions = {
            entry.package: self.decisions[entry.package]
            for entry in self.trail
            if entry.cause is None
        }
        self.domains.clear()

        for entry in self.trail:
            current = self.domains.get(entry.package, UNCONSTRAINED)
            self.domains[entry.package] = current.intersection(entry.domain)

        self.level = level
