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
        assert "wat" in r
        assert not r.is_empty

    def test_full_no_arbitrary(self) -> None:
        r = VersionRange.full(admit_arbitrary=False)
        assert Version("1.0") in r
        assert "wat" not in r

    def test_empty(self) -> None:
        r = VersionRange.empty()
        assert r.is_empty
        assert Version("1.0") not in r
        assert "wat" not in r

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
        # Autodetected admission is stored as a region (the spec's own bounds);
        # a non-pre-release spec leaves the region empty.
        assert vr(">=1.0a1")._pre_region == vr(">=1.0a1")._bounds
        assert vr(">=1.0a1")._pre_region
        assert vr(">=1.0")._pre_region == ()

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

    def test_union_full_preserves_autodetected_prerelease_policy(self) -> None:
        r = vr(">=1.0a1")
        assert list(r.filter(["1.3", "1.5a1"])) == ["1.3", "1.5a1"]

        # Both orders keep the autodetected opt-in as a region (here r's own
        # bounds), so only the pre-releases r named are admitted, not every
        # pre-release.
        assert (r | VersionRange.full())._pre_region == r._bounds
        assert (VersionRange.full() | r)._pre_region == r._bounds

        assert list((r | VersionRange.full()).filter(["1.3", "1.5a1"])) == [
            "1.3",
            "1.5a1",
        ]
        assert list((VersionRange.full() | r).filter(["1.3", "1.5a1"])) == [
            "1.3",
            "1.5a1",
        ]

        # The opt-in region is [1.0a1, +inf): a pre-release that sorts below it
        # is not force-admitted by the union.
        assert list((r | VersionRange.full()).filter(["0.5a1", "1.0"])) == ["1.0"]

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
        r = VersionRange.full() & vr("===wat")
        assert "wat" in r
        assert Version("1.0") not in r

    def test_complement_of_arbitrary_range(self) -> None:
        # nab complements root ranges built from ``===`` requirements.
        r = vr("===custom")
        assert not (~r).is_empty

    def test_empty_does_not_revive_arbitrary_admission(self) -> None:
        # ``~full()`` is empty yet keeps an inert arbitrary flag so that
        # ``~~full() == full()``. That flag must not revive and admit arbitrary
        # strings once a later operation widens the bounds back to full.
        full = VersionRange.full()
        plain = VersionRange.full(admit_arbitrary=False)
        assert ~~full == full  # the inert flag round-trips through complement
        assert (full & ~full) == VersionRange.empty()
        # The empty operand must not revive the flag from either side of a union,
        # nor through a difference that later complements back to full bounds.
        assert not (~full | plain).contains("wat")
        assert not (plain | ~full).contains("wat")
        assert (full & ~full) - full == VersionRange.empty()
        assert not (full - plain).complement().contains("wat")

    def test_difference_by_empty_keeps_arbitrary_admission(self) -> None:
        # ``~full()`` admits nothing (empty bounds, no literal, no region), so the
        # difference short-circuit returns self untouched, keeping full's
        # arbitrary admission (``full() - ~full() == full()``).
        full = VersionRange.full()
        assert (full - ~full) == full
        assert (full - ~full).contains("wat")

    def test_policy_mismatch_raises(self) -> None:
        with pytest.raises(ValueError, match="different"):
            vr(">=1.0", prereleases=True) & vr("<2.0", prereleases=False)

    def test_operator_wrong_type(self) -> None:
        assert vr(">=1.0").__and__("x") is NotImplemented
        assert vr(">=1.0").__or__("x") is NotImplemented
        assert vr(">=1.0").__sub__("x") is NotImplemented

    def test_intersection_wrong_type_raises(self) -> None:
        with pytest.raises(TypeError, match="expected VersionRange"):
            vr(">=1.0").intersection("x")  # type: ignore[arg-type]

    def test_difference_wrong_type_raises(self) -> None:
        with pytest.raises(TypeError, match="expected VersionRange"):
            vr(">=1.0").difference("x")  # type: ignore[arg-type]

    def test_difference(self) -> None:
        d = vr(">=1.0") - vr(">=2.0")
        assert Version("1.5") in d
        assert Version("1.0") in d
        assert Version("2.0") not in d
        assert d == vr(">=1.0") & ~vr(">=2.0")

    def test_difference_method_matches_operator(self) -> None:
        assert vr(">=1.0").difference(vr(">=2.0")) == vr(">=1.0") - vr(">=2.0")

    def test_difference_with_empty_is_self(self) -> None:
        r = vr(">=1.0,<2.0")
        assert (r - VersionRange.empty()) == r

    def test_difference_with_full_is_empty(self) -> None:
        assert (vr(">=1.0") - VersionRange.full()).is_empty

    def test_difference_keeps_minuend_prerelease_policy(self) -> None:
        # ``>=1.0`` admits no pre-releases; subtracting a pre-release-naming
        # range must not grant pre-release admission.
        no_pre = vr(">=1.0") - vr(">=2.0b1")
        assert list(no_pre.filter(["2.0b1", "1.5a1", "1.0"])) == ["1.0"]
        # A pre-release-admitting minuend keeps admitting its pre-releases.
        keep = vr(">=2.0b1") - vr(">=3.0")
        assert list(keep.filter(["2.5", "2.0b1"])) == ["2.5", "2.0b1"]

    def test_difference_requires_matching_policy(self) -> None:
        # difference matches ``self & ~other``, which requires a shared
        # configured policy, so a mismatch raises like intersection and union.
        with pytest.raises(ValueError, match="different"):
            vr(">=1.0") - vr(">=2.0", prereleases=True)

    def test_difference_punches_hole(self) -> None:
        # Subtracting an interior range leaves two intervals.
        d = vr(">=1.0") - vr(">=2.0,<3.0")
        assert Version("1.5") in d
        assert Version("2.5") not in d
        assert Version("3.5") in d

    def test_difference_with_literals(self) -> None:
        # ``===`` literal ranges route through the literal-combining branch.
        assert Version("1.0") in (vr("===1.0") - vr("===2.0"))
        assert Version("2.0") not in (vr("===1.0") - vr("===2.0"))
        assert Version("1.0") in (vr("===1.0") - vr(">=2.0"))

    def test_difference_with_empty_preserves_arbitrary(self) -> None:
        # Regression: difference once routed through ``other.complement()``,
        # which dropped the minuend's arbitrary-string admission even when
        # nothing was subtracted. ``a - empty`` must round-trip the full range.
        full = VersionRange.full()
        assert (full - VersionRange.empty()) == full
        assert "wat" in (full - VersionRange.empty())

    def test_difference_with_empty_preserves_literals(self) -> None:
        # The same regression for ``===`` admission: a literal range minus the
        # empty range keeps its literal.
        wat = vr("===wat")
        assert (wat - VersionRange.empty()) == wat
        assert "wat" in (wat - VersionRange.empty())

    def test_difference_excludes_only_named_literal(self) -> None:
        # full() minus a ``===`` literal keeps every version and every other
        # arbitrary string, dropping only the excluded literal.
        d = VersionRange.full() - vr("===wat")
        assert "wat" not in d
        assert "custom" in d
        assert Version("1.0") in d

    def test_difference_with_self_is_empty(self) -> None:
        # ``a - a`` is empty for arbitrary-admitting and ``===`` ranges too.
        assert (vr("===wat") - vr("===wat")).is_empty
        assert (VersionRange.full() - VersionRange.full()).is_empty

    def test_difference_minuend_with_reject_literal(self) -> None:
        # Complementing a ``===`` range leaves a reject literal on the minuend;
        # difference keeps honoring it through the literal-combining branch.
        minuend = ~vr("===1.0")
        d = minuend - vr("===2.0")
        assert Version("3.0") in d
        assert Version("1.0") not in d
        assert Version("2.0") not in d


class TestPrereleaseRegion:
    """The autodetected pre-release opt-in is stored as a range (``_pre_region``),
    clipped to the bounds, so it stays attached to the versions it came from
    across set algebra and never reaches past them."""

    def test_union_keeps_opt_in_scoped_to_originating_range(self) -> None:
        # ``>=1.0 | >=2.0b1``: the opt-in came only from the ``>=2.0b1`` side, so
        # a pre-release below 2.0b1 is not force-admitted, while pre-releases at
        # or above it are.
        u = vr(">=1.0") | vr(">=2.0b1")
        assert list(u.filter(["1.0", "1.5b1", "2.0b1", "2.5", "2.5b1"])) == [
            "1.0",
            "2.0b1",
            "2.5",
            "2.5b1",
        ]
        assert u._pre_region == vr(">=2.0b1")._bounds

    def test_narrowing_permanently_sheds_out_of_bounds_opt_in(self) -> None:
        # The region is clipped to the bounds, so a narrowing intersection drops
        # the opt-in that fell outside; a later widening cannot bring it back.
        inter = vr(">=1.0a1") & vr("<1.5")
        assert inter._pre_region == inter._bounds  # clipped to [1.0a1, 1.5)
        assert list(inter.filter(["1.2a1", "2.0a1", "2.5"])) == ["1.2a1"]
        # 2.0a1 is back in bounds but no longer in the region, so it is buffered
        # and then suppressed by the in-bounds final 2.5.
        wide = inter | vr("<3.0")
        assert list(wide.filter(["1.2a1", "2.0a1", "2.5"])) == ["1.2a1", "2.5"]

    def test_difference_of_two_region_bearing_ranges(self) -> None:
        # Both operands carry an opt-in region; a - b still equals a & ~b.
        a, b = vr(">=1.0a1,<5.0"), vr(">=2.0b1")
        cand = ["1.0a1", "1.5b1", "2.0b1", "2.5b1", "4.0"]
        assert (a - b) == (a & ~b)
        assert list((a - b).filter(cand)) == list((a & ~b).filter(cand))

    def test_intersection_with_complement_equals_difference(self) -> None:
        # ``a & ~b`` grants none of b's opt-in (complement drops it) just as
        # ``a - b`` does, so the two agree even when b names a pre-release.
        a, b = vr(">=1.0"), vr(">=2.0b1")
        cand = ["1.0", "1.5b1", "2.0b1", "2.5", "2.5b1"]
        assert (a & ~b) == (a - b)
        assert list((a & ~b).filter(cand)) == list((a - b).filter(cand))
        assert list((a & ~b).filter(cand)) == ["1.0"]

    def test_full_intersection_keeps_operand_opt_in(self) -> None:
        # ``full() & req`` must preserve req's own opt-in region.
        req = vr(">=2.0b1")
        assert (VersionRange.full() & req)._pre_region == req._bounds
        assert list((VersionRange.full() & req).filter(["2.0b1", "2.5"])) == [
            "2.0b1",
            "2.5",
        ]

    def test_union_filter_buffers_as_one_set(self) -> None:
        # The union is a single range: an in-range final makes PEP 440 buffer
        # away a non-opted pre-release, even though one operand alone (with no
        # final) would have emitted it. The opted-in pre-release still shows.
        u = vr(">=1.0,<1.8") | vr(">=1.5b1,<2.0")
        assert list(u.filter(["1.2a1", "1.7b1", "1.9"])) == ["1.7b1", "1.9"]

    def test_union_filter_emits_buffered_prerelease_when_no_final(self) -> None:
        # Region narrower than bounds: a pre-release in bounds but outside the
        # opt-in region is buffered, then emitted because no in-bounds final
        # appears (the PEP 440 "only available" fallback). An in-bounds final
        # then suppresses the buffer.
        u = vr(">=1.0") | vr(">=2.0b1")  # bounds [1.0, inf), region [2.0b1, inf)
        assert list(u.filter(["1.5b1", "1.2a1"])) == ["1.5b1", "1.2a1"]
        assert list(u.filter(["1.5b1", "1.2a1", "1.3"])) == ["1.3"]

    def test_double_complement_drops_region_keeps_versions(self) -> None:
        # A complement is an exclusion and carries no opt-in, so a double
        # complement covers the same versions as the original yet force-admits
        # none of its pre-releases.
        r = vr(">=2.0b1")
        assert (~~r)._bounds == r._bounds
        assert (~~r)._pre_region == ()
        cand = ["1.5b1", "2.0b1", "2.5", "2.5b1"]
        assert list(r.filter(cand)) == ["2.0b1", "2.5", "2.5b1"]
        assert list((~~r).filter(cand)) == ["2.5"]

    def test_difference_minuend_with_literal_and_region(self) -> None:
        # A minuend carrying both a ``===`` literal and an autodetected opt-in
        # region keeps the literal (self-admits-and-not-other) and the region.
        minuend = vr("===wat") | vr(">=2.0b1")
        d = minuend - vr(">=3.0")
        assert "wat" in d
        assert list(d.filter(["2.0b1", "2.5b1", "2.9", "3.0"])) == [
            "2.0b1",
            "2.5b1",
            "2.9",
        ]

    def test_difference_minuend_with_configured_policy(self) -> None:
        # A configured policy governs globally and carries no opt-in region, so a
        # difference between two configured operands keeps no region. Both must
        # share the policy, as intersection and union require.
        d = vr(">=1.0", prereleases=False) - vr(">=2.0b1", prereleases=False)
        assert d._pre_region == ()
        assert list(d.filter(["1.5b1", "1.0"])) == ["1.0"]

    def test_difference_equals_intersect_complement_when_b_complement_derived(
        self,
    ) -> None:
        # ``a - b == a & ~b`` even when ``b`` is complement-derived: a complement
        # carries no opt-in region, so both spellings admit none of ~b's in-bounds
        # pre-releases. (Two region-bearing operands are covered above.)
        a = vr("<5.0")
        b = vr(">=2.0b1").complement()
        left, right = a & ~b, a - b
        assert left._pre_region == right._pre_region
        assert left == right
        cand = ["2.5b1", "3.0", "2.0b1", "4.0"]
        assert list(left.filter(cand)) == list(right.filter(cand))

    def test_construction_region_matches_algebra(self) -> None:
        # A multi-specifier set built directly carries the same opt-in region as
        # one built by combining its specifiers: clipping refolds under
        # intersection, so the two stay equal under a later widening.
        direct = vr(">=1.0a1,<3.0")
        composed = vr(">=1.0a1") & vr("<3.0")
        assert direct._pre_region == composed._pre_region
        assert direct == composed
        pool = ["1.0a1", "2.0b1", "2.9", "3.0b1", "4.5"]
        wide = vr(">=2.0,<5.0")
        assert list((direct | wide).filter(pool)) == list(
            (composed | wide).filter(pool)
        )

        # Same congruence on the ``===`` (arbitrary) build path.
        direct_arb = vr("===2.0,>=1.0a1")
        composed_arb = vr("===2.0") & vr(">=1.0a1")
        assert direct_arb._pre_region == composed_arb._pre_region
        assert direct_arb == composed_arb

    def test_named_literal_prerelease_is_force_admitted(self) -> None:
        # A ``===`` literal naming a pre-release force-admits it under the default
        # policy even when a final release in the union would otherwise buffer it
        # away. contains agrees, and an explicit prereleases=False still drops it.
        u = vr("===1.0a1") | vr(">=3.0")
        assert list(u.filter(["1.0a1", "3.0"])) == ["1.0a1", "3.0"]
        assert u.contains("1.0a1")
        assert list(u.filter(["1.0a1", "3.0"], prereleases=False)) == ["3.0"]

    def test_difference_by_empty_preserves_empty_self(self) -> None:
        # ``a - empty()`` returns a unchanged even when a is itself empty but
        # carries provenance: ``~full()`` keeps its arbitrary flag for involution,
        # so subtracting a nothing-admitting set must not drop it.
        nf = ~VersionRange.full()
        assert (nf - VersionRange.empty()) == nf
        assert (nf - nf) == nf  # ~full() admits nothing, so this is a no-op too

    def test_difference_excludes_other_by_bounds(self) -> None:
        # difference treats other as a bounds-only exclusion: with a shared
        # configured policy it excises the versions in other's bounds and agrees
        # with a & ~b there.
        a = SpecifierSet(">=1.0", prereleases=False).to_range()
        b = SpecifierSet(">=1.5,<2.0", prereleases=False).to_range()
        assert (a - b) == (a & ~b)
        assert "1.2" in (a - b)
        assert "1.6" not in (a - b)

    def test_empty_bounds_intersection_equals_empty(self) -> None:
        # A region is clipped to the bounds, so an intersection with empty bounds
        # can carry none: it equals empty() and cannot re-admit anything after a
        # re-widening union.
        empty_region = vr(">=2.0a1") & vr("<1.0")
        assert empty_region.is_empty
        assert empty_region._pre_region == ()
        assert empty_region == VersionRange.empty()
        assert hash(empty_region) == hash(VersionRange.empty())
        assert list((empty_region | vr(">=0")).filter(["2.0a1", "3.0"])) == ["3.0"]

    def test_multi_interval_region_force_admits(self) -> None:
        # Disjoint multi-interval bounds with a two-interval opt-in region
        # exercise the multi-range path of filter_by_ranges: a pre-release inside
        # the region is force-admitted in either interval.
        r = vr(">=1.0a1,<2.0") | vr(">=3.0a1,<4.0")
        assert len(r._bounds) == 2
        assert list(r.filter(["1.5a1", "3.5a1", "3.5"])) == ["1.5a1", "3.5a1", "3.5"]

    def test_region_upper_bound_clips_force_admit(self) -> None:
        # The region has a finite upper bound (~=1.0a1 gives [1.0a1, 2.dev0)), so a
        # pre-release in bounds but ABOVE the region is not force-admitted. After
        # widening with >=2.5, 2.6a1 is in bounds yet above the region, so it is
        # buffered and then suppressed by the in-bounds final 2.7.
        r = vr("~=1.0a1") | vr(">=2.5")
        assert list(r.filter(["1.5a1", "2.6a1", "2.7"])) == ["1.5a1", "2.7"]

    def test_disjoint_region_does_not_force_admit_gap(self) -> None:
        # A disjoint two-interval region whose bounds span the gap: a pre-release
        # in the region gap (but in bounds) is buffered, not force-admitted, and
        # an in-bounds final then suppresses it. The filler ``>=2.0,<5.0`` widens
        # the bounds over the gap without adding to the region.
        r = (vr("<2.0a5") | vr(">=5.0a1")) | vr(">=2.0,<5.0")
        assert len(r._pre_region) == 2
        assert list(r.filter(["1.0a1", "3.0a1", "6.0a1", "3.0"])) == [
            "1.0a1",
            "6.0a1",
            "3.0",
        ]

    def test_force_admit_does_not_suppress_buffer(self) -> None:
        # A region-admitted pre-release is not a final, so it does not suppress a
        # separate buffered (out-of-region) pre-release when no final appears.
        u = vr(">=1.0") | vr(">=2.0b1")  # region [2.0b1, inf)
        assert list(u.filter(["2.5b1", "1.5b1"])) == ["2.5b1", "1.5b1"]

    def test_region_force_admit_through_key(self) -> None:
        # The region force-admit fires when filtering with a key callable too.
        u = vr(">=1.0") | vr(">=2.0b1")
        items = [{"v": "2.0b1"}, {"v": "1.5b1"}, {"v": "2.5"}]
        assert list(u.filter(items, key=lambda d: d["v"])) == [
            {"v": "2.0b1"},
            {"v": "2.5"},
        ]

    def test_difference_keeps_minuend_region_clipped(self) -> None:
        # difference keeps the minuend's opt-in region (not the subtrahend's) and
        # clips it to the result bounds.
        a = vr(">=2.0b1")  # region [2.0b1, +inf)
        b = vr(">=5.0")  # no region
        d = a - b
        assert d._pre_region == d._bounds  # clipped to [2.0b1, 5.0)
        assert list(d.filter(["2.0b1", "2.5b1", "4.9", "5.0"])) == [
            "2.0b1",
            "2.5b1",
            "4.9",
        ]

    def test_difference_by_empty_bounds_range(self) -> None:
        # An empty-bounds range carries no region under clipping, so subtracting
        # it is a no-op that still equals a & ~b (~empty == full).
        a = vr(">=0,<10.0")
        b = vr(">=2.0a1") & vr("<1.0")  # empty bounds, no region
        assert b.is_empty
        assert not b._bounds
        assert b._pre_region == ()
        cand = ["2.0a1", "2.5a1", "5.0"]
        assert (a - b) == (a & ~b) == a
        assert list((a - b).filter(cand)) == list((a & ~b).filter(cand))

    def test_configured_policy_with_prerelease_spec_mirrors_specifier_set(self) -> None:
        # A configured policy on a pre-release-naming set drops the opt-in region
        # (the policy governs); filter and contains still mirror the set.
        pool = ["1.0a1", "1.5", "2.0b1", "2.5"]
        cases = [
            (">=1.0a1", False),
            (">=1.0a1", True),
            ("~=2.0b1", True),
            ("<=2.0b1", False),
            ("===1.0a1", False),
            ("===1.0a1", True),
        ]
        for spec, pre in cases:
            ss = SpecifierSet(spec, prereleases=pre)
            r = ss.to_range()
            assert r._pre_region == ()
            assert list(r.filter(pool)) == list(ss.filter(pool)), (spec, pre)
            for v in pool:
                assert r.contains(v) == ss.contains(v), (spec, pre, v)


class TestUnionOverflowRegression:
    """Clipping the region to the bounds keeps a union or difference from
    force-admitting a pre-release no operand opted in (the leak that closed the
    PR #1304 attempt)."""

    def test_pr1304_union_example(self) -> None:
        # PR #1304's motivating example: the opt-in came only from ``>=2.0b1``,
        # so 1.5b1 is not force-admitted by the union.
        u = vr(">=1.0") | vr(">=2.0b1")
        assert list(u.filter(["1.0", "1.5b1", "2.0b1", "2.5"])) == [
            "1.0",
            "2.0b1",
            "2.5",
        ]

    def test_union_does_not_admit_out_of_bounds_prerelease(self) -> None:
        # Neither operand admits 3.6b1: ``>=3.5,<4`` has no opt-in and
        # ``>=2.0b1,<3`` opts in only below 3. Before clipping, the raw
        # [2.0b1, +inf) region rode the union past its own <3 cap onto 3.6b1.
        a, b = vr(">=3.5,<4"), vr(">=2.0b1,<3")
        assert list(a.filter(["3.6b1", "3.7"])) == ["3.7"]
        assert list(b.filter(["3.6b1", "3.7"])) == []
        assert list((a | b).filter(["3.6b1", "3.7"])) == ["3.7"]

    def test_difference_does_not_admit_out_of_bounds_prerelease(self) -> None:
        # The same overflow rides difference when the minuend carries it: the
        # [2.0b1, <3) opt-in must not reach 3.95a1 up in the [3.9, 4.0) interval.
        m = vr(">=2.0b1,<3") | vr(">=3.9,<4.0")
        assert list((m - vr(">=2,<3.9")).filter(["3.95a1", "3.97"])) == ["3.97"]


class TestDeliberateNonIdentities:
    """Laws that clip trades away, each with the canonical witness. These are
    negative locks: a future change that restores double complement (and, by
    T2, the union leak) flips them and fails here."""

    def test_absorption_keeps_inner_opt_in(self) -> None:
        # L7/L8: a & (a | b) and a | (a & b) keep b's opt-in inside a's bounds,
        # so they do not collapse back to a.
        a, b = vr(">=1.0"), vr(">=2.0b1")
        cand = ["2.5b1", "3.0"]
        assert a & (a | b) != a
        assert list((a & (a | b)).filter(cand)) == ["2.5b1", "3.0"]
        assert a | (a & b) != a
        assert list((a | (a & b)).filter(cand)) == ["2.5b1", "3.0"]
        assert list(a.filter(cand)) == ["3.0"]

    def test_union_does_not_distribute_over_intersection(self) -> None:
        # L10: a | (b & c) carries less opt-in than (a | b) & (a | c).
        a, b, c = vr(">=1.0"), vr(">=2.0b1,<3"), vr(">=3.5")
        lhs = a | (b & c)
        rhs = (a | b) & (a | c)
        assert lhs != rhs
        assert list(lhs.filter(["2.5b1", "2.6"])) == ["2.6"]
        assert list(rhs.filter(["2.5b1", "2.6"])) == ["2.5b1", "2.6"]

    def test_double_complement_is_erasure_not_identity(self) -> None:
        # L11: ~~b keeps b's versions but drops its opt-in, so it is not b.
        b = vr(">=2.0b1")
        assert ~~b != b
        assert (~~b)._pre_region == ()
        assert b._pre_region

    def test_excluded_middle_and_union_with_full_overshoot(self) -> None:
        # L16/L28: a | ~a and a | full() carry a's opt-in, which full() (with no
        # eager admission) does not, so neither equals full().
        b = vr(">=2.0b1")
        assert b | ~b != VersionRange.full()
        assert b | VersionRange.full() != VersionRange.full()

    def test_double_difference_sheds_opt_in(self) -> None:
        # L24: a - (a - b) drops b's opt-in (each difference is an exclusion),
        # while a & b keeps it.
        a, b = vr(">=1.0"), vr(">=2.0b1")
        assert a - (a - b) != a & b
        assert (a - (a - b))._pre_region == ()
        assert (a & b)._pre_region


class TestSetRelations:
    def test_disjoint_false(self) -> None:
        assert not vr(">=1.0,<2.0").is_disjoint(vr(">=1.5,<2.5"))

    def test_disjoint_higher_range_on_left(self) -> None:
        # The receiver sits entirely above the argument, including when the
        # argument spans several intervals.
        assert vr(">=2.0,<3.0").is_disjoint(vr(">=1.0,<1.5"))
        assert vr(">=5.0,<6.0").is_disjoint(vr(">=1.0,<2.0") | vr(">=3.0,<4.0"))

    def test_disjoint_shared_inclusive_endpoint(self) -> None:
        # ``[1, 2)`` and ``[2, 3)`` touch but share no version.
        assert vr(">=1.0,<2.0").is_disjoint(vr(">=2.0,<3.0"))
        # ``[1, 2]`` and ``[2, 3)`` both admit 2.0.
        assert not vr(">=1.0,<=2.0").is_disjoint(vr(">=2.0,<3.0"))

    def test_subset_true(self) -> None:
        assert vr(">=1.5,<1.8").is_subset(vr(">=1.0,<2.0"))

    def test_subset_false(self) -> None:
        assert not vr(">=1.0,<2.0").is_subset(vr(">=1.5,<1.8"))

    def test_subset_partial_overlap_false(self) -> None:
        assert not vr(">=1.0,<2.0").is_subset(vr(">=1.5,<2.5"))

    def test_subset_reflexive(self) -> None:
        r = vr(">=1.0,<2.0")
        assert r.is_subset(r)

    def test_empty_is_subset_of_everything(self) -> None:
        assert VersionRange.empty().is_subset(vr(">=1.0"))
        assert VersionRange.empty().is_subset(VersionRange.empty())
        assert VersionRange.empty().is_disjoint(vr(">=1.0"))

    def test_nonempty_not_subset_of_empty(self) -> None:
        assert not vr(">=1.0").is_subset(VersionRange.empty())

    def test_everything_is_subset_of_full(self) -> None:
        assert vr(">=1.0,<2.0").is_subset(VersionRange.full())

    def test_superset_mirrors_subset(self) -> None:
        outer, inner = vr(">=1.0,<2.0"), vr(">=1.5,<1.8")
        assert outer.is_superset(inner)
        assert not inner.is_superset(outer)
        assert outer.is_superset(inner) == inner.is_subset(outer)

    def test_multi_interval_subset(self) -> None:
        # ``!=1.5`` splits ``[1, 2)`` into two pieces, still inside ``[1, 2)``.
        gapped = vr(">=1.0,<2.0,!=1.5")
        whole = vr(">=1.0,<2.0")
        assert gapped.is_subset(whole)
        assert not whole.is_subset(gapped)
        assert not gapped.is_disjoint(whole)

    def test_disjoint_nonempty_excludes_subset(self) -> None:
        a, b = vr(">=1.0,<2.0"), vr(">=3.0,<4.0")
        assert a.is_disjoint(b)
        assert not a.is_subset(b)

    def test_literal_ranges_disjoint(self) -> None:
        assert vr("===a").is_disjoint(vr("===b"))
        assert not vr("===a").is_disjoint(vr("===a"))

    def test_literal_range_subset(self) -> None:
        # is_subset is ``self - other``, so a literal only ``self`` admits keeps
        # it from being a subset. ``self & ~other`` would miss this, since
        # complement is one-way for ``===`` literals.
        a = vr("===a")
        ab = vr("===a") | vr("===b")

        assert a.is_subset(ab)
        assert not ab.is_subset(a)

        assert ab.is_superset(a)
        assert not a.is_superset(ab)

    def test_full_arbitrary_matches_algebra(self) -> None:
        # ``full()`` carries the arbitrary-string flag, so it is not plain and
        # both relations take the non-plain path.
        f, b = VersionRange.full(), vr(">=1.0")

        assert not f.is_subset(b)
        assert b.is_subset(f)

        # Disjointness still mirrors the intersection algebra directly.
        assert f.is_disjoint(b) == (f & b).is_empty

    def test_prerelease_excluding_policy_matches_algebra(self) -> None:
        # ``prereleases=False`` ranges are not plain, so both relations take
        # the algebra fallback; pin concrete non-trivial answers there.
        inner = vr(">=1.2,<1.8", prereleases=False)
        outer = vr(">=1.0,<2.0", prereleases=False)
        far = vr(">=5.0,<6.0", prereleases=False)
        assert inner.is_subset(outer)
        assert not outer.is_subset(inner)
        assert inner.is_disjoint(far)
        assert not inner.is_disjoint(outer)
        for a, b in [(inner, outer), (outer, inner), (inner, far)]:
            assert a.is_subset(b) == (a & ~b).is_empty
            assert a.is_disjoint(b) == (a & b).is_empty

    def test_policy_mismatch_raises(self) -> None:
        with pytest.raises(ValueError, match="different"):
            vr(">=1.0", prereleases=True).is_subset(vr("<2.0", prereleases=False))
        with pytest.raises(ValueError, match="different"):
            vr(">=1.0", prereleases=True).is_disjoint(vr("<2.0", prereleases=False))
        with pytest.raises(ValueError, match="different"):
            vr(">=1.0", prereleases=True).is_superset(vr("<2.0", prereleases=False))

    def test_wrong_type_raises(self) -> None:
        with pytest.raises(TypeError, match="expected VersionRange"):
            vr(">=1.0").is_subset("x")  # type: ignore[arg-type]
        with pytest.raises(TypeError, match="expected VersionRange"):
            vr(">=1.0").is_disjoint("x")  # type: ignore[arg-type]
        with pytest.raises(TypeError, match="expected VersionRange"):
            vr(">=1.0").is_superset("x")  # type: ignore[arg-type]


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
        r = VersionRange.full() & vr("===wat")
        # admit literal then a non-matching final
        assert list(r.filter(["wat", "1.0"])) == ["wat"]

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
        assert not vr(">=1.0").contains("wat")

    def test_contains_unparsable_full(self) -> None:
        assert VersionRange.full().contains("wat")

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
        # range (its complement is empty). It still carries an opt-in region from
        # its .dev0 bound, so it is not equal to the region-free full().
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
        # Two ranges with identical bounds but a different opt-in region must NOT
        # compare equal, so equal ranges always filter the same.
        autodetect_true = vr(">=1.0a1") & vr(">=2.0")  # opt-in region [1.0a1, inf)
        autodetect_none = vr(">=2.0")  # empty opt-in region
        assert autodetect_true._bounds == autodetect_none._bounds
        assert autodetect_true != autodetect_none
        assert hash(autodetect_true) != hash(autodetect_none)
        assert list(autodetect_true.filter(["2.0", "2.5a1"])) != list(
            autodetect_none.filter(["2.0", "2.5a1"])
        )

    def test_eq_full_region_mismatch(self) -> None:
        # Same bounds and arbitrary flag but a different opt-in region must stay
        # unequal, so the two never substitute for each other. ``>=0.dev0`` names
        # a pre-release across the whole line, so it carries a full opt-in region;
        # ``full(admit_arbitrary=False)`` carries none.
        b = vr(">=0.dev0")
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
