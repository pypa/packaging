# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.

from __future__ import annotations

import pytest

from packaging._ranges import BoundaryKind, BoundaryVersion
from packaging.ranges import VersionRange
from packaging.specifiers import SpecifierSet
from packaging.version import InvalidVersion, Version


def vr(spec: str, prereleases: bool | None = None) -> VersionRange:
    return SpecifierSet(spec, prereleases=prereleases).to_range()


class TestConstruction:
    def test_cannot_construct_directly(self) -> None:
        with pytest.raises(TypeError, match="cannot create"):
            VersionRange()

    def test_full(self) -> None:
        r = VersionRange.full()
        assert Version("1.0") in r
        assert "garbage" in r
        assert not r.is_empty

    def test_full_no_arbitrary(self) -> None:
        r = VersionRange.full(admit_arbitrary=False)
        assert Version("1.0") in r
        assert "garbage" not in r

    def test_empty(self) -> None:
        r = VersionRange.empty()
        assert r.is_empty
        assert Version("1.0") not in r
        assert "garbage" not in r

    def test_empty_with_prereleases(self) -> None:
        r = VersionRange.empty(prereleases=True)
        assert r.is_empty
        assert r._prereleases_configured is True

    def test_full_with_prereleases(self) -> None:
        r = VersionRange.full(prereleases=False)
        assert r._prereleases_configured is False

    def test_singleton(self) -> None:
        r = VersionRange.singleton("1.2.3")
        assert Version("1.2.3") in r
        assert Version("1.2.4") not in r

    def test_singleton_is_strict(self) -> None:
        # ``==1.0`` matches 1.0+local; the strict singleton does not.
        assert Version("1.0+local") not in VersionRange.singleton("1.0")
        assert Version("1.0+local") in vr("==1.0")

    def test_singleton_accepts_version(self) -> None:
        assert Version("1.0") in VersionRange.singleton(Version("1.0"))

    def test_singleton_with_prereleases(self) -> None:
        r = VersionRange.singleton("1.0", prereleases=True)
        assert r._prereleases_configured is True

    def test_singleton_invalid(self) -> None:
        with pytest.raises(InvalidVersion):
            VersionRange.singleton("not a version")

    def test_singleton_floor_is_canonical_and_strict(self) -> None:
        # ``0.dev0`` is the minimum version, so the strict singleton collapses
        # its floor to the one canonical form ``(-inf, 0.dev0]`` while keeping
        # strict-equality semantics (locals and higher versions excluded).
        r = VersionRange.singleton("0.dev0")
        assert Version("0.dev0") in r
        assert Version("0.dev0+local") not in r
        assert Version("0") not in r
        # Floor collapsed: the lower bound is unbounded (-inf), not [0.dev0.
        assert r._bounds[0][0].version is None

    def test_singleton_above_floor_stays_strict(self) -> None:
        # ``0`` sorts above ``0.dev0`` (the floor), so its singleton must not
        # collapse: ``(-inf, 0]`` would wrongly admit ``0.dev0``.
        r = VersionRange.singleton("0")
        assert Version("0.dev0") not in r
        assert Version("0") in r


class TestToRange:
    def test_any(self) -> None:
        r = SpecifierSet().to_range()
        assert Version("1.0") in r
        assert Version("999.0") in r

    def test_unsatisfiable(self) -> None:
        assert SpecifierSet(">=2.0,<1.0").to_range().is_empty

    @pytest.mark.parametrize(
        ("spec", "inside", "outside"),
        [
            (">=1.0", "1.0", "0.9"),
            (">1.0", "1.1", "1.0"),
            ("<=1.0", "1.0", "1.1"),
            ("<1.0", "0.9", "1.0"),
            ("==1.0", "1.0", "1.1"),
            ("!=1.5", "1.4", "1.5"),
            ("~=1.4.2", "1.4.5", "1.5"),
            ("==1.2.*", "1.2.9", "1.3"),
        ],
    )
    def test_operators(self, spec: str, inside: str, outside: str) -> None:
        r = vr(spec)
        assert Version(inside) in r
        assert Version(outside) not in r

    def test_lte_includes_local_excludes_post(self) -> None:
        r = vr("<=1.0")
        assert Version("1.0") in r
        assert Version("1.0+local") in r
        assert Version("1.0.post1") not in r

    def test_gt_excludes_post(self) -> None:
        r = vr(">1.0")
        assert Version("1.0") not in r
        assert Version("1.0.post1") not in r
        assert Version("1.0.1") in r

    def test_arbitrary_equality_literal_range(self) -> None:
        # The nab carve-out contract: the literal string matches, no Version.
        r = vr("===1.0.special")
        assert "1.0.special" in r
        assert Version("1.0") not in r

    def test_arbitrary_equality_valid_version_literal(self) -> None:
        r = vr("===1.0")
        assert Version("1.0") in r
        assert Version("1.0.0") not in r  # arbitrary string, not version, match

    def test_arbitrary_combined_with_bounds(self) -> None:
        # ``===1.0,>=2.0``: only candidate "1.0" cannot satisfy >=2.0.
        assert vr("===1.0,>=2.0").is_empty

    def test_prerelease_autodetect(self) -> None:
        assert vr(">=1.0a1")._prereleases is True
        assert vr(">=1.0")._prereleases is None

    def test_explicit_prereleases(self) -> None:
        r = vr(">=1.0", prereleases=False)
        assert r._prereleases_configured is False


class TestSetAlgebra:
    def test_intersection(self) -> None:
        assert vr(">=1.0") & vr("<2.0") == vr(">=1.0,<2.0")
        assert vr(">=1.0").intersection(vr("<2.0")) == vr(">=1.0,<2.0")

    def test_union(self) -> None:
        u = VersionRange.singleton("1.0") | VersionRange.singleton("2.0")
        assert Version("1.0") in u
        assert Version("2.0") in u
        assert Version("1.5") not in u
        assert VersionRange.singleton("1.0").union(VersionRange.singleton("2.0")) == u

    def test_complement(self) -> None:
        r = vr(">=1.0")
        assert Version("0.5") in r.complement()
        assert Version("1.5") not in r.complement()
        assert r.complement().complement() == r
        assert (~r) == r.complement()

    def test_complement_full_is_empty(self) -> None:
        assert (~VersionRange.full(admit_arbitrary=False)).is_empty

    def test_floor_singleton_obeys_structural_laws(self) -> None:
        # The ``0.dev0`` floor singleton used to keep a non-canonical
        # ``[0.dev0, ...)`` lower through set algebra, breaking these laws
        # structurally (the version set was always correct).
        s = VersionRange.singleton("0.dev0")
        assert s.complement().complement() == s
        assert s.union(s.complement()) == VersionRange.full(admit_arbitrary=False)
        assert s.union(s) == s

    def test_union_with_empty_preserves(self) -> None:
        r = vr(">=1.0")
        assert (r | VersionRange.empty()) == r

    def test_intersection_with_full_preserves_arbitrary(self) -> None:
        r = vr(">=1.0")
        assert (r & VersionRange.full()) == r

    def test_union_full_collapses(self) -> None:
        # ``r | full()`` collapses to the canonical universal range.
        r = VersionRange.singleton("1.0")
        collapsed = r | VersionRange.full()
        assert collapsed == VersionRange.full()

    def test_union_full_keeps_explicit_policy(self) -> None:
        r = VersionRange.singleton("1.0", prereleases=True)
        collapsed = r | VersionRange.full(prereleases=True)
        assert collapsed._prereleases_configured is True

    def test_arbitrary_flag_distinguishes_full(self) -> None:
        # nab contract: SpecifierSet("")-full differs from algebra-built full.
        flagged_full = SpecifierSet("").to_range()
        exact = VersionRange.singleton(Version("1.0"))
        plain_full = exact | ~exact
        assert plain_full != flagged_full
        assert (flagged_full & ~plain_full).is_empty

    def test_intersection_two_arbitrary(self) -> None:
        assert (vr("===a") & vr("===b")).is_empty
        assert "a" in (vr("===a") & vr("===a"))

    def test_union_two_arbitrary(self) -> None:
        u = vr("===a") | vr("===b")
        assert "a" in u
        assert "b" in u

    def test_full_intersect_arbitrary_keeps_literal(self) -> None:
        r = VersionRange.full() & vr("===garbage")
        assert "garbage" in r
        assert Version("1.0") not in r

    def test_complement_of_arbitrary_range(self) -> None:
        # nab complements root ranges built from ``===`` requirements.
        r = vr("===custom")
        assert not (~r).is_empty

    def test_policy_mismatch_raises(self) -> None:
        with pytest.raises(ValueError, match="different"):
            vr(">=1.0", prereleases=True) & vr("<2.0", prereleases=False)

    def test_operator_wrong_type(self) -> None:
        assert vr(">=1.0").__and__("x") is NotImplemented
        assert vr(">=1.0").__or__("x") is NotImplemented

    def test_intersection_wrong_type_raises(self) -> None:
        with pytest.raises(TypeError, match="expected VersionRange"):
            vr(">=1.0").intersection("x")  # type: ignore[arg-type]


class TestFilter:
    def test_filter_bounds(self) -> None:
        assert list(vr(">=1.0,<2.0").filter(["0.9", "1.5", "2.0"])) == ["1.5"]

    def test_filter_prereleases_default_buffers(self) -> None:
        assert list(vr(">=1.0").filter(["1.3", "1.5a1"])) == ["1.3"]
        assert list(vr(">=1.0").filter(["1.5a1"])) == ["1.5a1"]

    def test_filter_prereleases_true(self) -> None:
        assert list(vr(">=1.0").filter(["1.3", "1.5a1"], prereleases=True)) == [
            "1.3",
            "1.5a1",
        ]

    def test_filter_prereleases_false(self) -> None:
        assert list(vr(">=1.0").filter(["1.3", "1.5a1"], prereleases=False)) == ["1.3"]

    def test_filter_autodetect_true(self) -> None:
        assert list(vr(">=1.0a1").filter(["1.0a1", "1.5"])) == ["1.0a1", "1.5"]

    def test_filter_key(self) -> None:
        items = [{"v": "1.0"}, {"v": "2.0"}]
        out = list(vr("<2.0").filter(items, key=lambda x: x["v"]))
        assert out == [{"v": "1.0"}]

    def test_filter_universal(self) -> None:
        assert list(VersionRange.full().filter(["1.3", "1.5a1"])) == ["1.3"]
        assert list(VersionRange.full().filter(["1.5a1"])) == ["1.5a1"]
        assert list(VersionRange.full().filter(["1.3"], prereleases=True)) == ["1.3"]
        assert list(VersionRange.full().filter(["1.5a1"], prereleases=False)) == []
        assert list(VersionRange.full().filter(["junk", "1.0"])) == ["junk", "1.0"]
        assert list(VersionRange.full().filter(["junk"])) == ["junk"]

    def test_filter_admission_modes(self) -> None:
        r = vr("===1.5a1")
        assert list(r.filter(["1.5a1"], prereleases=True)) == ["1.5a1"]
        assert list(r.filter(["1.5a1"], prereleases=False)) == []
        assert list(r.filter(["1.5a1"])) == ["1.5a1"]

    def test_filter_admission_with_final(self) -> None:
        r = VersionRange.full() & vr("===garbage")
        # admit literal then a non-matching final
        assert list(r.filter(["garbage", "1.0"])) == ["garbage"]

    def test_filter_admission_reject(self) -> None:
        r = ~vr("===1.0")
        assert list(r.filter(["1.0", "2.0"])) == ["2.0"]


class TestContains:
    def test_contains_version_and_str(self) -> None:
        r = vr(">=1.0,<2.0")
        assert r.contains("1.5")
        assert r.contains(Version("1.5"))
        assert not r.contains("2.0")

    def test_contains_prereleases_false(self) -> None:
        assert not vr(">=1.0").contains("1.5a1", prereleases=False)
        assert vr(">=1.0").contains("1.5a1", prereleases=True)

    def test_contains_installed(self) -> None:
        r = vr(">=1.0", prereleases=False)
        assert r.contains("1.5a1", installed=True)
        assert r.contains(Version("1.5a1"), installed=True)
        assert r.contains("1.5", installed=True)

    def test_contains_arbitrary_literal(self) -> None:
        r = vr("===wat")
        assert r.contains("wat")
        assert r.contains("WAT")  # case-insensitive
        assert not r.contains("other")

    def test_contains_literal_prerelease_excluded(self) -> None:
        r = vr("===1.0a1", prereleases=False)
        assert not r.contains("1.0a1")

    def test_contains_literal_prerelease_autodetect(self) -> None:
        r = vr("===1.0a1")
        assert r.contains("1.0a1")

    def test_contains_unparsable_non_full(self) -> None:
        assert not vr(">=1.0").contains("garbage")

    def test_contains_unparsable_full(self) -> None:
        assert VersionRange.full().contains("garbage")

    def test_contains_reject(self) -> None:
        r = ~vr("===1.0")
        assert not r.contains("1.0")
        assert r.contains("2.0")

    def test_contains_typeerror(self) -> None:
        with pytest.raises(TypeError, match="expected str or Version"):
            vr(">=1.0").contains(123)  # type: ignore[arg-type]


class TestEquality:
    def test_eq_and_hash(self) -> None:
        a = vr(">=1.0,<2.0")
        b = vr(">=1.0,<2.0")
        assert a == b
        assert hash(a) == hash(b)
        assert len({a, b}) == 1

    def test_eq_wrong_type(self) -> None:
        assert vr(">=1.0").__eq__("x") is NotImplemented
        assert vr(">=1.0") != "x"

    def test_neq_bounds(self) -> None:
        assert vr(">=1.0") != vr(">=2.0")

    @pytest.mark.parametrize(
        ("spec", "expected"),
        [
            (">=1.0,<2.0", "<VersionRange '[1.0, 2.0.dev0)'>"),
            ("", "<VersionRange '(-inf, +inf)' arbitrary>"),
            (">=2.0,<1.0", "<VersionRange '(empty)'>"),
        ],
    )
    def test_repr(self, spec: str, expected: str) -> None:
        assert repr(SpecifierSet(spec).to_range()) == expected

    def test_repr_arbitrary_literal(self) -> None:
        assert repr(vr("===wat")) == "<VersionRange '{wat}'>"

    def test_repr_reject(self) -> None:
        assert "\\" in repr(~vr("===1.0"))

    def test_repr_pre(self) -> None:
        assert "pre=False" in repr(vr(">=1.0", prereleases=False))

    def test_repr_boundary_kinds(self) -> None:
        assert "AFTER_LOCALS" in repr(vr("==1.0"))
        assert "AFTER_POSTS" in repr(vr(">1.0"))


# Boundary-sensitive specs and versions exercising the union / complement /
# empty-check edge branches deterministically.
_GRID_SPECS = [
    "",
    ">=1.0,<2.0",
    "!=1.5",
    "~=1.4.2",
    "==1.*",
    "==2.*",
    "==2.0.*",
    "==1.2.*",
    "==1.2.3.*",
    "!=1.0",
    "!=1.5.*",
    ">1.0.post1",
    "<=1.0.post2",
    "==1.0+local",
    "!=1.0+local",
    ">=1.0a1",
    "<1.0rc1",
    "==2!1.0",
    ">=2!1.0",
    "<2!1.0",
    ">=1.0.dev0",
    "!=1.0.dev0",
    "==1.0.dev0",
    "!=1.0a1",
    "<1.0",
    ">1.0",
    "===wat",
    "===1.0",
]

_GRID_VERSIONS = [
    "0.dev0",
    "0",
    "1.0.dev0",
    "1.0a1",
    "1.0rc1",
    "1.0",
    "1.0+local",
    "1.0.post0",
    "1.0.post1",
    "1.0.post2",
    "1.0.1",
    "1.2",
    "1.2.3",
    "1.4.2",
    "1.4.9",
    "1.5",
    "1.5.1",
    "1.6",
    "2.0.dev0",
    "2.0",
    "2!1.0",
    "3.0",
]


_GRID_RANGES = [SpecifierSet(s).to_range() for s in _GRID_SPECS]
_GRID_VERSION_OBJS = [Version(v) for v in _GRID_VERSIONS]


class TestAlgebraInvariants:
    """Membership invariants over an exhaustive small grid.

    Every range here is autodetect (configured policy None), so ``contains``
    on a :class:`Version` reduces to pure bounds membership and the set-algebra
    identities hold exactly.
    """

    def _same_versions(self, a: VersionRange, b: VersionRange) -> bool:
        return all((v in a) == (v in b) for v in _GRID_VERSION_OBJS)

    def test_complement_is_negation(self) -> None:
        for r in _GRID_RANGES:
            comp = ~r
            for v in _GRID_VERSION_OBJS:
                assert (v in comp) == (v not in r), (r, v)

    def test_double_complement_matches(self) -> None:
        # ``~~r`` matches the same versions as ``r``. It is structurally equal
        # for canonical ranges; the degenerate ``>=0.dev0`` canonicalizes to
        # the full range, which is version-equivalent.
        for r in _GRID_RANGES:
            assert self._same_versions(~~r, r), r

    def test_intersection_is_and(self) -> None:
        for a in _GRID_RANGES:
            for b in _GRID_RANGES:
                ab = a & b
                for v in _GRID_VERSION_OBJS:
                    assert (v in ab) == ((v in a) and (v in b)), (a, b, v)

    def test_union_is_or(self) -> None:
        for a in _GRID_RANGES:
            for b in _GRID_RANGES:
                ab = a | b
                for v in _GRID_VERSION_OBJS:
                    assert (v in ab) == ((v in a) or (v in b)), (a, b, v)


class TestSyntheticEmptyGaps:
    """Intervals that are ordered yet hold no real version.

    ``>V`` excludes V's post-releases (AFTER_POSTS) and ``<=V`` includes V's
    locals (AFTER_LOCALS), so a bound can sit just below the next real version.
    When the opposite bound lands on that successor, the interval is ordered but
    empty: ``>1.0a1`` admits nothing below ``1.0a2.dev0`` because every
    ``1.0a1.postN`` is excluded. The empty interval must be detected so that
    ``is_empty``, equality, and the set algebra stay correct.
    """

    @pytest.mark.parametrize(
        "spec",
        [
            ">1.0a1,<1.0a2.dev0",  # AFTER_POSTS pre-release, next pre-release
            ">1.0a0,<1.0a1.dev0",
            ">1.0b0,<1.0b1.dev0",
            ">1.0rc1,<1.0rc2.dev0",
            ">1!1.0a1,<1!1.0a2.dev0",  # epoch carried through
            ">1.0,<1.0.post0.dev0",  # AFTER_POSTS final, below its post0.dev0
        ],
    )
    def test_is_empty(self, spec: str) -> None:
        assert SpecifierSet(spec).to_range().is_empty

    @pytest.mark.parametrize(
        "spec",
        [
            ">1.0a2,<1.0b0.dev0",  # 1.0a3.dev0 sits between
            ">1.5,<2",  # 1.5.1.dev0 sits between
            ">1.0,<1.0.0.1",  # 1.0.0.0.1.dev0 sits between
            ">1.0a1,<1.0a2",  # 1.0a2.dev0 sits between
        ],
    )
    def test_not_empty(self, spec: str) -> None:
        assert not SpecifierSet(spec).to_range().is_empty

    def test_equal_substitutability(self) -> None:
        # Equality is substitutability: two synthetic-empty ranges match no
        # version, so they compare equal (both reduce to empty bounds).
        a = vr(">1.0a1,<1.0a2.dev0")
        b = vr(">1.0b0,<1.0b1.dev0")
        assert a == b
        assert hash(a) == hash(b)
        assert a._bounds == ()

    def test_subset_of_anything(self) -> None:
        # The PubGrub subset test ``(a & ~b).is_empty``: the empty set is a
        # subset of every range.
        empty = vr(">1.0a1,<1.0a2.dev0")
        assert (empty & ~vr(">=5.0")).is_empty

    @pytest.mark.parametrize(
        ("spec", "excluded"),
        [
            ("!=1.0,<1.0.post0.dev0", "1.0"),  # AFTER_LOCALS, post0 successor
            ("!=1.0.post3,<1.0.post4.dev0", "1.0.post3"),  # post(N+1) successor
            ("!=1.0.dev5,<1.0.dev6", "1.0.dev5"),  # dev(N+1) successor
        ],
    )
    def test_intersection_drops_embedded_empty(self, spec: str, excluded: str) -> None:
        # The empty AFTER_LOCALS interval must not survive in the bounds.
        r = SpecifierSet(spec).to_range()
        assert len(r._bounds) == 1
        assert not r.is_empty
        assert Version(excluded) not in r

    def test_complement_of_covering_union_is_empty(self) -> None:
        # ``~(>1.0a1)`` (everything up to and including 1.0a1's posts) and
        # ``>=1.0a2.dev0`` leave only the empty gap uncovered, so the union is
        # everything and its complement is empty.
        covering = ~vr(">1.0a1") | vr(">=1.0a2.dev0")
        assert covering._bounds == VersionRange.full()._bounds
        assert covering.complement().is_empty

    def test_double_complement_of_empty(self) -> None:
        r = vr(">1.0a1,<1.0a2.dev0")
        assert (~~r).is_empty


class TestBoundaryCanonicalization:
    """Different specifiers for the same set canonicalize to one form.

    ``>1.0a1`` excludes ``1.0a1``'s post-releases, so its smallest member is
    ``1.0a2.dev0``, exactly what ``>=1.0a2.dev0`` starts at. The two are the
    same set, so they fold to one boundary form and compare equal. The boundary
    (non-``.dev0``) form is canonical, so ``>=1.0a2.dev0`` adopts ``>1.0a1``'s.
    """

    @pytest.mark.parametrize(
        ("dev_form", "boundary_form"),
        [
            # Both operands are pre-releases, so the pair shares one pre-release
            # policy and equality reduces to the (identical) version set.
            (">=1.0a2.dev0", ">1.0a1"),  # AFTER_POSTS pre-release
            (">=1!1.0a2.dev0", ">1!1.0a1"),  # epoch carried through
            (">=1.0a1.post1.dev0", ">1.0a1.post0"),  # AFTER_LOCALS post(N+1)
            (">=1.0a1.dev6", ">1.0a1.dev5"),  # AFTER_LOCALS dev(N+1)
            (">=1.0.dev6", ">1.0.dev5"),  # AFTER_LOCALS dev on a final base
            (">=1.0a1.post1.dev6", ">1.0a1.post1.dev5"),  # AFTER_LOCALS post+dev
            (">=1.0.post0.dev1", ">1.0.post0.dev0"),  # post+dev on a final base
        ],
    )
    def test_equal_and_hash(self, dev_form: str, boundary_form: str) -> None:
        a, b = vr(dev_form), vr(boundary_form)
        assert a == b
        assert hash(a) == hash(b)
        assert a._bounds == b._bounds
        assert len({a, b}) == 1

    def test_upper_bound_folds_to_boundary(self) -> None:
        # The exclusive-upper mirror: ``<1.0a2.dev0`` ends at AFTER_POSTS(1.0a1).
        assert "1.0a1[AFTER_POSTS]" in repr(vr("<1.0a2.dev0"))

    def test_keeps_non_dev_anchor(self) -> None:
        # The boundary form is canonical, so the repr keeps the non-dev anchor.
        assert "1.0a1[AFTER_POSTS]" in repr(vr(">=1.0a2.dev0"))

    def test_prerelease_policy_keeps_them_distinct(self) -> None:
        # Same set, but ``<1.0.post0.dev0`` admits pre-releases by default and
        # ``<=1.0`` does not, so they are not substitutable and stay unequal.
        assert vr("<1.0.post0.dev0") != vr("<=1.0")

    def test_plain_version_is_not_folded(self) -> None:
        # ``1.0a2`` is not a boundary successor, so ``>=1.0a2`` stays plain.
        assert "1.0a2" in repr(vr(">=1.0a2"))
        assert "AFTER" not in repr(vr(">=1.0a2"))


class TestEmptyMatchesUnsatisfiable:
    """``is_empty`` agrees with ``SpecifierSet.is_unsatisfiable``.

    Both fold in the pre-release policy: a range whose only members are
    pre-releases is empty when the policy excludes them.
    """

    @pytest.mark.parametrize(
        "spec",
        [
            "==1.0a1",
            "===1.0a1",
            "==1.0a1,==1.0a1",
            "==0.dev0",  # floor: only member 0.dev0 is a pre-release
            "<0.dev1",  # floor: nothing below 0.dev1 but the pre-release 0.dev0
        ],
    )
    def test_prerelease_only_empty_when_policy_excludes(self, spec: str) -> None:
        assert vr(spec, prereleases=False).is_empty
        assert not vr(spec, prereleases=True).is_empty
        assert SpecifierSet(spec, prereleases=False).is_unsatisfiable()

    def test_non_prerelease_literal_survives(self) -> None:
        # ``===1.0`` admits a final release, so the policy does not empty it.
        assert not vr("===1.0", prereleases=False).is_empty

    @pytest.mark.parametrize(
        "spec", [">=1.0", ">=1.0a1.post0,<=1.0", ">=1.0.post0.dev0,<=1.0.post0"]
    )
    def test_non_prerelease_bounds_survive(self, spec: str) -> None:
        # A pre-release-with-post lower still admits the final/post release.
        assert not vr(spec, prereleases=False).is_empty

    def test_arbitrary_admission_is_not_empty(self) -> None:
        # The universal range admits any string regardless of policy.
        assert not vr("", prereleases=False).is_empty


class TestCoverageEdges:
    """Targeted cases for branches the grid does not reach."""

    def test_build_admit_and_reject(self) -> None:
        r = (vr("===a") | vr("===b")) & vr("===a")
        assert "a" in r
        assert "b" not in r

    def test_combine_literal_reject(self) -> None:
        # Version literals so the reject set survives _build against full bounds.
        r = (~vr("===1.0")) | vr("===2.0")
        assert Version("2.0") in r
        assert Version("1.5") in r
        assert Version("1.0") not in r

    def test_filter_literal_nonmatching_string(self) -> None:
        assert list(vr("===wat").filter(["other"])) == []

    def test_filter_admission_false_mixed(self) -> None:
        r = ~vr("===1.0")
        assert list(r.filter(["1.0", "2.0"], prereleases=False)) == ["2.0"]

    def test_filter_admission_arbitrary_after_final(self) -> None:
        r = vr(">=1.0") | vr("===wat")
        assert list(r.filter(["1.5", "wat"])) == ["1.5", "wat"]

    def test_filter_admission_prerelease_buffer(self) -> None:
        r = vr(">=1.0") | vr("===wat")
        assert list(r.filter(["1.5a1", "wat"])) == ["1.5a1", "wat"]

    def test_contains_literal_nonprerelease_false_policy(self) -> None:
        assert vr("===1.0", prereleases=False).contains("1.0")

    def test_after_posts_boundary_total_order_consistent(self) -> None:
        # ``AFTER_POSTS(1.0)`` and ``AFTER_POSTS(1.0.post1)`` mark the same point
        # on the version line, so equality must agree with the ordering:
        # exactly one of ``<``, ``==``, ``>`` holds for any two boundaries.
        a = BoundaryVersion(Version("1.0"), BoundaryKind.AFTER_POSTS)
        b = BoundaryVersion(Version("1.0.post1"), BoundaryKind.AFTER_POSTS)
        assert a == b
        assert hash(a) == hash(b)
        assert (a < b) + (a == b) + (a > b) == 1

        # Distinct points stay unequal and strictly ordered, and the two kinds
        # at one version are different points.
        c = BoundaryVersion(Version("1.1"), BoundaryKind.AFTER_POSTS)
        assert a != c
        assert (a < c) ^ (a > c)
        assert a != BoundaryVersion(Version("1.0"), BoundaryKind.AFTER_LOCALS)

    def test_arbitrary_after_locals_dev(self) -> None:
        # !=1.0.dev0 produces an AFTER_LOCALS(1.0.dev0) boundary with a dev
        # inner version, exercising the dev successor path under complement.
        r = ~vr("!=1.0.dev0")
        assert Version("1.0.dev0") in r
        assert Version("1.1") not in r

    def test_double_complement_min_boundary(self) -> None:
        # >=0.dev0 is already canonicalized to the full range at construction,
        # so ~~ round-trips it (full -> empty -> full).
        r = vr(">=0.dev0")
        comp2 = ~~r
        for v in ["0.dev0", "0", "1.0", "2!1.0"]:
            assert (Version(v) in comp2) == (Version(v) in r)

    def test_sub_minimum_union(self) -> None:
        # Union touching the 0.dev0 floor exercises the sub-minimum empty check.
        r = vr("==0.dev0") | vr(">=1.0")
        assert Version("0.dev0") in r
        assert Version("1.0") in r
        assert Version("0.5") not in r

    def test_ge_floor_is_canonical_full(self) -> None:
        # >=0.dev0 admits every version, so its bounds canonicalize to the full
        # range (its complement is empty). It keeps its autodetected pre-release
        # policy, so it is not equal to the policy-free full().
        r = vr(">=0.dev0")
        assert r._bounds == VersionRange.full()._bounds
        assert (~r).is_empty

    def test_ne_floor_drops_empty_leading_interval(self) -> None:
        # !=0.dev0's lower (-inf, 0.dev0) interval is empty (sub-floor) and is
        # dropped, leaving only the upper half.
        r = vr("!=0.dev0")
        assert Version("0.dev0") not in r
        assert Version("1.0") in r
        assert Version("0") in r

    def test_complement_singleton_floor(self) -> None:
        # ~singleton(0.dev0): the empty (-inf, 0.dev0) leading gap is dropped.
        r = ~VersionRange.singleton("0.dev0")
        assert not r.is_empty
        assert Version("0.dev0") not in r
        assert Version("1.0") in r

    def test_eq_ranges_filter_identically(self) -> None:
        # Two ranges with identical bounds but different resolved pre-release
        # policy must NOT compare equal, so equal ranges always filter the same.
        autodetect_true = vr(">=1.0a1") & vr(">=2.0")  # resolved True, [2.0, inf)
        autodetect_none = vr(">=2.0")  # resolved None, [2.0, inf)
        assert autodetect_true._bounds == autodetect_none._bounds
        assert autodetect_true != autodetect_none
        assert hash(autodetect_true) != hash(autodetect_none)
        assert list(autodetect_true.filter(["2.0", "2.5a1"])) != list(
            autodetect_none.filter(["2.0", "2.5a1"])
        )

    def test_eq_full_resolved_mismatch(self) -> None:
        # The floor shape that exposed the substitutability bug.
        b = ~~vr(">=0.dev0")
        c = VersionRange.full(admit_arbitrary=False)
        assert b._bounds == c._bounds
        assert b._admit_arbitrary == c._admit_arbitrary
        assert b != c
        assert list(b.filter(["0.dev0", "1.0"])) != list(c.filter(["0.dev0", "1.0"]))

    def test_filter_universal_false_yields_final(self) -> None:
        assert list(
            VersionRange.full().filter(["1.0", "1.5a1"], prereleases=False)
        ) == ["1.0"]

    def test_filter_universal_unparsable_after_final(self) -> None:
        assert list(VersionRange.full().filter(["1.0", "junk"])) == ["1.0", "junk"]

    def test_complement_zero_singleton(self) -> None:
        r = ~vr("==0")
        assert Version("0") not in r
        assert Version("1.0") in r

    def test_complement_post_boundary(self) -> None:
        # AFTER_LOCALS boundary adjacent to its post successor.
        r = ~vr("==1.0") | vr("==1.0.post0")
        assert Version("1.0") not in r
        assert Version("1.0.post0") in r
        assert Version("2.0") in r

    def test_union_after_locals_successor_merge(self) -> None:
        # ==1.0 upper (AFTER_LOCALS) meets 1.0.post0.dev0: the empty gap merges.
        r = vr("==1.0") | vr(">=1.0.post0.dev0")
        assert Version("1.0") in r
        assert Version("1.0.post0") in r
        assert Version("0.9") not in r

    def test_filter_universal_two_finals(self) -> None:
        assert list(VersionRange.full().filter(["1.0", "2.0"])) == ["1.0", "2.0"]

    def test_filter_admission_true_skips_rejected(self) -> None:
        r = ~vr("===1.0")
        assert list(r.filter(["1.0", "2.0"], prereleases=True)) == ["2.0"]

    def test_filter_admission_two_finals(self) -> None:
        r = vr(">=1.0") | vr("===wat")
        assert list(r.filter(["1.5", "2.5"])) == ["1.5", "2.5"]

    def test_filter_admission_prerelease_after_final(self) -> None:
        r = vr(">=1.0") | vr("===wat")
        assert list(r.filter(["1.5", "2.5a1"])) == ["1.5"]
