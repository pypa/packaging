# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.

"""Property tests verifying ``VersionRange`` satisfies PubGrub's invariants.

Each test class quotes the relevant paragraph verbatim from one of:

* `solver.md`_, the Dart pub specification (`Definitions Term`_,
  `Definitions Incompatibility`_).
* `Pubgrub blog post`_, Natalie Weizenbaum, 2018.

Unicode set-theoretic operators in the quotations are preserved as
written; the per-file ``noqa`` overrides silence ruff's ambiguous-glyph
warning for those quotations only.

.. _solver.md: https://github.com/dart-lang/pub/blob/master/doc/solver.md
.. _Definitions Term:
   https://github.com/dart-lang/pub/blob/master/doc/solver.md#term
.. _Definitions Incompatibility:
   https://github.com/dart-lang/pub/blob/master/doc/solver.md#incompatibility
.. _Pubgrub blog post: https://nex3.medium.com/pubgrub-2fb6470504f
"""

# ruff: noqa: RUF002, RUF003, E501
# RUF002 / RUF003: ambiguous Unicode in docstrings and comments, the
#         spec quotations preserve set-theoretic operators verbatim.
# E501: spec quotations are reproduced as written; wrapping them would
#       harm searchability against the upstream documents.

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from hypothesis import given

from packaging.ranges import VersionRange

from .strategies import SETTINGS, VERSION_POOL, pep440_versions, specifier_sets

if TYPE_CHECKING:
    from packaging.specifiers import SpecifierSet
    from packaging.version import Version

pytestmark = pytest.mark.property


def _to_range(spec_set: SpecifierSet) -> VersionRange:
    """Lift a non-``===`` SpecifierSet into a VersionRange."""
    return spec_set.to_range()


def _term_set(range_: VersionRange, *, positive: bool) -> VersionRange:
    """Set view of a PubGrub term: ``R`` if positive, ``~R`` if negative."""
    return range_ if positive else range_.complement()


def _is_subset(a: VersionRange, b: VersionRange) -> bool:
    """``A ⊆ B`` iff ``A & B == A``."""
    return (a & b) == a


def _is_disjoint(a: VersionRange, b: VersionRange) -> bool:
    """``A ∩ B == ∅``."""
    return (a & b).is_empty


class TestQuoteTermAsStatement:
    """solver.md § Term, paragraph 1:

    > "The fundamental unit on which Pubgrub operates is a Term, which
    > represents a statement about a package that may be true or false
    > for a given selection of package versions. For example, foo
    > ^1.0.0 is a term that's true if foo 1.2.3 is selected and false
    > if foo 2.3.4 is selected. Conversely, not foo ^1.0.0 is false if
    > foo 1.2.3 is selected and true if foo 2.3.4 is selected or if no
    > version of foo is selected at all."
    """

    @given(spec_set=specifier_sets())
    @SETTINGS
    def test_positive_and_negative_polarities_disagree_pointwise(
        self, spec_set: SpecifierSet
    ) -> None:
        """``v in R`` iff ``v not in ~R`` for every PEP 440 version."""
        r = _to_range(spec_set)
        positive = _term_set(r, positive=True)
        negative = _term_set(r, positive=False)
        for v in VERSION_POOL:
            assert (v in positive) is not (v in negative)


class TestQuoteTermsDenoteSets:
    """solver.md § Term, paragraph 4:

    > "Terms can be viewed as denoting sets of allowed versions, with
    > negative terms denoting the complement of the corresponding
    > positive term. Set relations and operations can be defined
    > accordingly."
    """

    @given(spec_set=specifier_sets())
    @SETTINGS
    def test_double_negation_returns_original_term(
        self, spec_set: SpecifierSet
    ) -> None:
        """``not not T == T``."""
        r = _to_range(spec_set)
        assert _term_set(_term_set(r, positive=False), positive=False) == r


class TestQuoteSetOperationExamples:
    """solver.md § Term, paragraph 5:

    > "* foo ^1.0.0 ∪ foo ^2.0.0 is foo >=1.0.0 <3.0.0.
    > * foo >=1.0.0 ∩ not foo >=2.0.0 is foo ^1.0.0.
    > * foo ^1.0.0 \\ foo ^1.5.0 is foo >=1.0.0 <1.5.0."
    """

    @given(a=specifier_sets(), b=specifier_sets())
    @SETTINGS
    def test_set_difference_equals_intersection_with_complement(
        self, a: SpecifierSet, b: SpecifierSet
    ) -> None:
        """``A \\ B`` (versions in A but not B) equals ``A ∩ ~B``."""
        ra, rb = _to_range(a), _to_range(b)
        difference = ra & rb.complement()
        for v in VERSION_POOL:
            assert (v in difference) == (v in ra and v not in rb)

    @given(a=specifier_sets(), b=specifier_sets())
    @SETTINGS
    def test_intersection_with_negation_excludes_negated_range(
        self, a: SpecifierSet, b: SpecifierSet
    ) -> None:
        """``v in A ∩ not B`` iff ``v in A`` and ``v not in B``."""
        ra, rb = _to_range(a), _to_range(b)
        result = ra & rb.complement()
        for v in VERSION_POOL:
            assert (v in result) == ((v in ra) and (v not in rb))


class TestQuoteSatisfiesAndContradictsIdentities:
    """solver.md § Term, paragraph 6:

    > "This turns out to be useful for computing satisfaction and
    > contradiction. Given a term t and a set of terms S, we have the
    > following identities:
    > * S satisfies t if and only if ⋂S ⊆ t.
    > * S contradicts t if and only if ⋂S is disjoint with t."
    """

    @given(s=specifier_sets(), t=specifier_sets())
    @SETTINGS
    def test_subset_implies_pointwise_satisfaction(
        self, s: SpecifierSet, t: SpecifierSet
    ) -> None:
        """Structural ``⋂S ⊆ T`` implies every pooled version satisfying
        ``S`` also satisfies ``T``. Only this direction is sound: the
        finite pool makes the pointwise converse spuriously True."""
        rs, rt = _to_range(s), _to_range(t)
        if _is_subset(rs, rt):
            assert all((v not in rs) or (v in rt) for v in VERSION_POOL)

    @given(s=specifier_sets(), t=specifier_sets())
    @SETTINGS
    def test_disjoint_implies_pointwise_contradiction(
        self, s: SpecifierSet, t: SpecifierSet
    ) -> None:
        """Structural ``⋂S ∩ T == ∅`` implies no pooled version satisfies
        both ``S`` and ``T``. The pointwise converse is unsound on a
        finite pool, so only the forward direction is asserted."""
        rs, rt = _to_range(s), _to_range(t)
        if _is_disjoint(rs, rt):
            assert all((v not in rs) or (v not in rt) for v in VERSION_POOL)

    @given(s=specifier_sets(), t=specifier_sets())
    @SETTINGS
    def test_satisfies_iff_subset_negative(
        self, s: SpecifierSet, t: SpecifierSet
    ) -> None:
        """``S`` satisfies negative term ``not T`` iff ``⋂S ⊆ ~T``."""
        rs, rt = _to_range(s), _to_range(t)
        neg_t = _term_set(rt, positive=False)
        assert _is_subset(rs, neg_t) == _is_disjoint(rs, rt)

    @given(s=specifier_sets(), t=specifier_sets())
    @SETTINGS
    def test_contradicts_iff_disjoint_negative(
        self, s: SpecifierSet, t: SpecifierSet
    ) -> None:
        """``S`` contradicts negative term ``not T`` iff ``⋂S ⊆ T``."""
        rs, rt = _to_range(s), _to_range(t)
        neg_t = _term_set(rt, positive=False)
        assert _is_disjoint(rs, neg_t) == _is_subset(rs, rt)


class TestQuoteTrichotomy:
    """solver.md § Term, paragraph 2:

    > "We say that a set of terms S 'satisfies' a term t if t must be
    > true whenever every term in S is true. Conversely, S
    > 'contradicts' t if t must be false whenever every term in S is
    > true. If neither of these is true, we say that S is
    > 'inconclusive' for t. As a shorthand, we say that a term v
    > satisfies or contradicts t if {v} satisfies or contradicts it."
    """

    @given(s=specifier_sets(), t=specifier_sets())
    @SETTINGS
    def test_satisfies_and_contradicts_mutually_exclusive_on_non_empty(
        self, s: SpecifierSet, t: SpecifierSet
    ) -> None:
        """For non-empty ``⋂S``, ``S`` cannot both satisfy and contradict ``t``."""
        rs, rt = _to_range(s), _to_range(t)
        if rs.is_empty:
            return
        satisfies = _is_subset(rs, rt)
        contradicts = _is_disjoint(rs, rt)
        assert not (satisfies and contradicts)

    @given(s=specifier_sets(), t=specifier_sets())
    @SETTINGS
    def test_empty_intersection_is_both_satisfies_and_contradicts(
        self, s: SpecifierSet, t: SpecifierSet
    ) -> None:
        """An unsatisfiable ``S`` (``⋂S == ∅``) is vacuously both."""
        rs, rt = _to_range(s), _to_range(t)
        if not rs.is_empty:
            return
        assert _is_subset(rs, rt)
        assert _is_disjoint(rs, rt)

    @given(spec_set=specifier_sets())
    @SETTINGS
    def test_singleton_shorthand(self, spec_set: SpecifierSet) -> None:
        """``{v}`` satisfies ``t`` iff ``v in t``; trichotomy collapses on singletons."""
        rt = _to_range(spec_set)
        for v in VERSION_POOL:
            singleton = VersionRange.singleton(v)
            satisfies = _is_subset(singleton, rt)
            contradicts = _is_disjoint(singleton, rt)
            assert satisfies == (v in rt)
            assert contradicts == (v not in rt)
            assert satisfies != contradicts


class TestQuoteIncompatibilityNormalisation:
    """solver.md § Incompatibility, paragraph 2:

    > "Incompatibilities are normalized so that at most one term refers
    > to any given package name. For example, {foo >=1.0.0, foo
    > <2.0.0} is normalized to {foo ^1.0.0}. Derived incompatibilities
    > with more than one term are also normalized to remove positive
    > terms referring to the root package, since these terms will
    > always be satisfied."
    """

    @given(a=specifier_sets(), b=specifier_sets(), c=specifier_sets())
    @SETTINGS
    def test_three_term_merge_is_order_independent(
        self, a: SpecifierSet, b: SpecifierSet, c: SpecifierSet
    ) -> None:
        """Merging ``{R1, R2, R3}`` over the same package is order-free."""
        ra, rb, rc = _to_range(a), _to_range(b), _to_range(c)
        m1 = ra & rb & rc
        m2 = ra & rc & rb
        m3 = rb & ra & rc
        m4 = rb & rc & ra
        m5 = rc & ra & rb
        m6 = rc & rb & ra
        assert m1 == m2 == m3 == m4 == m5 == m6


class TestQuoteBlogPostSatisfaction:
    """nex3.medium.com/pubgrub, § "So What Does PubGrub Do?":

    > "A term is satisfied if it matches the version of the package
    > that's selected. menu ≥1.1.0 is satisfied if menu 1.2.0 is
    > selected, and not dropdown ≥2.0.0 is satisfied if dropdown 1.8.0
    > is selected (or if no version of dropdown is selected at all)."
    """

    @given(spec_set=specifier_sets(), v=pep440_versions())
    @SETTINGS
    def test_concrete_version_satisfies_negative_term_iff_outside_range(
        self, spec_set: SpecifierSet, v: Version
    ) -> None:
        """Negative ``not T`` satisfied by ``v`` iff ``v not in T``."""
        rt = _to_range(spec_set)
        negative_set = _term_set(rt, positive=False)
        assert (v in negative_set) == (v not in rt)


class TestQuoteConcreteExamples:
    """solver.md § Term, paragraph 3:

    > "* {foo >=1.0.0, foo <2.0.0} satisfies foo ^1.0.0,
    > * foo ^1.5.0 contradicts not foo ^1.0.0,
    > * and foo ^1.0.0 is inconclusive for foo ^1.5.0."
    """

    @given(spec_set=specifier_sets())
    @SETTINGS
    def test_self_subset_satisfies_self(self, spec_set: SpecifierSet) -> None:
        """``R`` satisfies ``R``."""
        r = _to_range(spec_set)
        assert _is_subset(r, r)

    @given(a=specifier_sets(), b=specifier_sets())
    @SETTINGS
    def test_subset_implies_contradicts_negation(
        self, a: SpecifierSet, b: SpecifierSet
    ) -> None:
        """``A ⊆ B`` implies ``A & ~B == ∅``."""
        ra, rb = _to_range(a), _to_range(b)
        if not _is_subset(ra, rb):
            return
        assert _is_disjoint(ra, rb.complement())

    @given(a=specifier_sets(), b=specifier_sets())
    @SETTINGS
    def test_strict_superset_is_inconclusive_for_subset(
        self, a: SpecifierSet, b: SpecifierSet
    ) -> None:
        """``B ⊊ A`` ⇒ ``A`` neither satisfies nor contradicts ``B``."""
        ra, rb = _to_range(a), _to_range(b)
        if rb.is_empty or not _is_subset(rb, ra) or ra == rb:
            return
        assert not _is_subset(ra, rb)
        assert not _is_disjoint(ra, rb)


class TestQuoteSetSatisfiesIncompatibility:
    """solver.md § Incompatibility, paragraph 3:

    > "We say that a set of terms S satisfies an incompatibility I if
    > S satisfies every term in I. We say that S contradicts I if S
    > contradicts at least one term in I. If S satisfies all but one
    > of I's terms and is inconclusive for the remaining term, we say
    > S 'almost satisfies' I and we call the remaining term the
    > 'unsatisfied term'."
    """

    @given(s=specifier_sets(), t1=specifier_sets(), t2=specifier_sets())
    @SETTINGS
    def test_satisfies_two_term_incompatibility_iff_subset_of_intersection(
        self, s: SpecifierSet, t1: SpecifierSet, t2: SpecifierSet
    ) -> None:
        """``S satisfies {t1, t2}`` iff ``⋂S ⊆ t1 ∩ t2``."""
        rs, r1, r2 = _to_range(s), _to_range(t1), _to_range(t2)
        sat_universal = _is_subset(rs, r1) and _is_subset(rs, r2)
        sat_via_intersection = _is_subset(rs, r1 & r2)
        assert sat_universal == sat_via_intersection

    @given(s=specifier_sets(), t1=specifier_sets(), t2=specifier_sets())
    @SETTINGS
    def test_contradicts_two_term_incompatibility_iff_disjoint_with_either(
        self, s: SpecifierSet, t1: SpecifierSet, t2: SpecifierSet
    ) -> None:
        """``S contradicts {t1, t2}`` iff ``⋂S ∩ t1 == ∅`` OR ``⋂S ∩ t2 == ∅``."""
        rs, r1, r2 = _to_range(s), _to_range(t1), _to_range(t2)
        cont_existential = _is_disjoint(rs, r1) or _is_disjoint(rs, r2)
        # Per-term subset-of-complement form. Strictly stronger than
        # ``⋂S ⊆ (~t1 ∪ ~t2)`` (the pointwise existential).
        cont_existential_alt = _is_subset(rs, r1.complement()) or _is_subset(
            rs, r2.complement()
        )
        assert cont_existential == cont_existential_alt
        # Incompatibility is a set of terms, so the disjunction is
        # order-free.
        cont_reversed = _is_disjoint(rs, r2) or _is_disjoint(rs, r1)
        assert cont_existential == cont_reversed
