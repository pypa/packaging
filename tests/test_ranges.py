# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.

from __future__ import annotations

import pickle

import pytest

from packaging._range_utils import BoundaryKind, BoundaryVersion
from packaging._version_utils import version_cmpkey
from packaging.ranges import VersionRange, _restore_version_range
from packaging.specifiers import Specifier, SpecifierSet
from packaging.version import Version


class TestDirectConstructionForbidden:
    def test_call_raises_type_error(self) -> None:
        with pytest.raises(TypeError, match="cannot create 'VersionRange' instances"):
            VersionRange()

    def test_call_with_args_raises_type_error(self) -> None:
        with pytest.raises(TypeError):
            VersionRange("anything")

    def test_call_with_kwargs_raises_type_error(self) -> None:
        with pytest.raises(TypeError):
            VersionRange(bounds=())

    def test_subclass_call_raises_too(self) -> None:
        # __new__ raises before any subclass __init__ runs.
        class Sub(VersionRange):
            pass

        with pytest.raises(TypeError):
            Sub()


class TestToRangeMethods:
    """``Specifier.to_range`` and ``SpecifierSet.to_range`` are
    convenience methods that delegate to the corresponding
    :class:`VersionRange` classmethod factories.  They must produce the
    same result as the factories."""

    def test_specifier_to_range(self) -> None:
        spec = Specifier(">=1.0")
        method_result = spec.to_range()
        factory_result = VersionRange.from_specifier(spec)
        assert method_result == factory_result
        assert "1.5" in method_result

    def test_specifier_set_to_range(self) -> None:
        ss = SpecifierSet(">=1.0,<2.0")
        method_result = ss.to_range()
        factory_result = VersionRange.from_specifier_set(ss)
        assert method_result == factory_result
        assert "1.5" in method_result

    def test_specifier_set_to_range_empty(self) -> None:
        r = SpecifierSet("").to_range()
        assert "0.1" in r

    def test_specifier_set_to_range_unsatisfiable(self) -> None:
        r = SpecifierSet(">=2,<1").to_range()
        assert r.is_empty


class TestFromSpecifier:
    def test_returns_version_range(self) -> None:
        r = VersionRange.from_specifier(Specifier(">=1.0"))
        assert isinstance(r, VersionRange)
        assert "1.0" in r
        assert "0.5" not in r

    def test_arbitrary_returns_carve_out_range(self) -> None:
        r = VersionRange.from_specifier(Specifier("===wat"))
        assert isinstance(r, VersionRange)
        assert r._admit == frozenset({"wat"})
        assert "wat" in r
        assert "WAT" in r
        assert "other" not in r

        r = VersionRange.from_specifier(Specifier("===1.0"))
        assert isinstance(r, VersionRange)
        assert r._admit == frozenset({"1.0"})
        assert "1.0" in r
        assert "1.0+local" not in r  # === is exact, unlike ==

    def test_arbitrary_supports_set_algebra(self) -> None:
        # ``===`` ranges propagate through the lattice on a slow path.
        # The result may not have a SpecifierSet representation, but
        # the operations always succeed.
        wat = VersionRange.from_specifier(Specifier("===wat"))
        full = VersionRange.full()
        assert wat.intersection(full) == wat
        assert wat.union(full) == full
        comp = wat.complement()
        assert "wat" not in comp
        assert "1.0" in comp
        assert comp.complement() == wat

    def test_unsatisfiable_returns_empty_range(self) -> None:
        # ``<V`` for V at the smallest possible version yields an empty
        # range, not None.
        r = VersionRange.from_specifier(Specifier("<0"))
        assert isinstance(r, VersionRange)
        assert r.is_empty

    def test_wildcard(self) -> None:
        r = VersionRange.from_specifier(Specifier("==1.2.*"))
        assert isinstance(r, VersionRange)
        assert "1.2" in r
        assert "1.2.3" in r
        assert "1.3" not in r
        assert "1.1" not in r

    def test_compatible_release(self) -> None:
        r = VersionRange.from_specifier(Specifier("~=1.2.3"))
        assert isinstance(r, VersionRange)
        assert "1.2.3" in r
        assert "1.2.99" in r
        assert "1.3" not in r

    def test_not_equal_disjoint(self) -> None:
        r = VersionRange.from_specifier(Specifier("!=1.5"))
        assert isinstance(r, VersionRange)
        assert "1.4" in r
        assert "1.5" not in r
        assert "1.6" in r


class TestFromSpecifierSet:
    def test_simple(self) -> None:
        r = VersionRange.from_specifier_set(SpecifierSet(">=1.0,<2.0"))
        assert isinstance(r, VersionRange)
        assert "1.5" in r
        assert "2.0" not in r

    def test_arbitrary_returns_carve_out_range(self) -> None:
        r = VersionRange.from_specifier_set(SpecifierSet("===wat"))
        assert isinstance(r, VersionRange)
        assert r._admit == frozenset({"wat"})
        assert "wat" in r
        assert "other" not in r

        # ``wat`` does not parse, so the conjunction with ``>=1`` is
        # empty and the literal tag is dropped (matched set is the
        # source of truth, not the spec text). Order does not matter.
        for spec in ("===wat,>=1", ">=1,===wat"):
            r = VersionRange.from_specifier_set(SpecifierSet(spec))
            assert isinstance(r, VersionRange)
            assert r._admit == frozenset()
            assert r.is_empty

    def test_empty_specifier_set_is_full_range(self) -> None:
        r = VersionRange.from_specifier_set(SpecifierSet(""))
        assert isinstance(r, VersionRange)
        assert "0.1" in r
        assert "999.0" in r

    def test_unsatisfiable_returns_empty_range(self) -> None:
        r = VersionRange.from_specifier_set(SpecifierSet(">=2,<1"))
        assert isinstance(r, VersionRange)
        assert r.is_empty

    def test_intersection_via_combine(self) -> None:
        ss = SpecifierSet(">=1.0,<3.0") & SpecifierSet(">=2.0,<4.0")
        r = VersionRange.from_specifier_set(ss)
        assert isinstance(r, VersionRange)
        assert "2.5" in r
        assert "1.5" not in r
        assert "3.5" not in r

    def test_caching_returns_same_object(self) -> None:
        # The range is cached on the SpecifierSet instance via
        # ``to_range``; repeated calls return the same object. The
        # stateless ``from_specifier_set`` factory builds fresh, equal
        # ranges instead.
        ss = SpecifierSet(">=1.0,<2.0")
        assert ss.to_range() is ss.to_range()
        assert VersionRange.from_specifier_set(ss) == ss.to_range()

    def test_caching_for_arbitrary_returns_same_object(self) -> None:
        ss = SpecifierSet("===wat")
        first = ss.to_range()
        second = ss.to_range()
        assert first is second
        assert first._admit == frozenset({"wat"})

    def test_cache_invalidates_on_canonicalize(self) -> None:
        # Iterating the iterable-built SpecifierSet triggers
        # canonicalization, which must invalidate the instance cache.
        ss = SpecifierSet([Specifier(">=1.0"), Specifier("<2.0"), Specifier(">=1.0")])
        first = ss.to_range()
        str(ss)  # force canonicalization
        second = ss.to_range()
        assert first == second

    def test_cache_invalidates_on_prereleases_setter(self) -> None:
        # The range does not depend on prereleases, so the recomputed
        # result is structurally equal.
        ss = SpecifierSet(">=1.0")
        first = ss.to_range()
        ss.prereleases = True
        assert ss.to_range() == first

    def test_combination_with_arbitrary_returns_carve_out(self) -> None:
        a = SpecifierSet(">=1.0")
        b = SpecifierSet("===wat")
        r = VersionRange.from_specifier_set(a & b)
        assert isinstance(r, VersionRange)
        assert r._admit == frozenset()
        assert r.is_empty


class TestContains:
    def test_simple_lower_inclusive(self) -> None:
        r = VersionRange.from_specifier_set(SpecifierSet(">=1.0,<2.0"))
        assert "1.0" in r
        assert "1.5" in r
        assert "2.0" not in r
        assert "0.9" not in r

    def test_simple_upper_inclusive(self) -> None:
        r = VersionRange.from_specifier_set(SpecifierSet(">1.0,<=2.0"))
        assert "1.0" not in r
        assert "1.5" in r
        assert "2.0" in r
        assert "2.0.1" not in r

    def test_disjoint_excluded(self) -> None:
        r = VersionRange.from_specifier_set(SpecifierSet(">=1.0,!=1.5"))
        assert "1.0" in r
        assert "1.4" in r
        assert "1.5" not in r
        assert "1.6" in r

    def test_empty_range_contains_nothing(self) -> None:
        r = VersionRange.from_specifier_set(SpecifierSet(">=2.0,<1.0"))
        assert "0.5" not in r
        assert "1.5" not in r
        assert "2.5" not in r

    def test_empty_intersection_short_circuits_remaining_specs(self) -> None:
        # ``>=2.0,<1.0`` already intersects to empty; the trailing
        # ``!=3.0`` then exercises the early-exit break.
        r = VersionRange.from_specifier_set(SpecifierSet(">=2.0,<1.0,!=3.0"))
        assert r.is_empty

    def test_full_range_contains_anything_parseable(self) -> None:
        r = VersionRange.from_specifier_set(SpecifierSet(""))
        assert "0.1" in r
        assert "999.0" in r
        assert "1.0a1" in r

    def test_unparsable_string_not_contained(self) -> None:
        r = VersionRange.from_specifier_set(SpecifierSet(">=1.0"))
        assert "not-a-version" not in r
        assert "" not in r

    def test_version_object(self) -> None:
        r = VersionRange.from_specifier_set(SpecifierSet(">=1.0,<2.0"))
        assert Version("1.5") in r
        assert Version("2.0") not in r

    def test_local_segment_handling(self) -> None:
        # PEP 440: <=1.0 includes 1.0+local
        r = VersionRange.from_specifier_set(SpecifierSet("<=1.0"))
        assert "1.0" in r
        assert "1.0+local" in r

    def test_post_release_excluded_by_gt(self) -> None:
        # PEP 440: >1.0 excludes 1.0.postN
        r = VersionRange.from_specifier_set(SpecifierSet(">1.0"))
        assert "1.0" not in r
        assert "1.0.post1" not in r
        assert "1.1" in r


class TestEmpty:
    @pytest.mark.parametrize(
        ("spec", "expected_empty"),
        [
            (">=2,<1", True),
            (">=1,<2", False),
            ("", False),
        ],
    )
    def test_is_empty_matches_bool(self, spec: str, expected_empty: bool) -> None:
        r = VersionRange.from_specifier_set(SpecifierSet(spec))
        assert r.is_empty is expected_empty
        assert bool(r) is not expected_empty


class TestEquality:
    def test_same_range_equal(self) -> None:
        r1 = VersionRange.from_specifier_set(SpecifierSet(">=1.0,<2.0"))
        r2 = VersionRange.from_specifier_set(SpecifierSet(">=1.0,<2.0"))
        assert r1 == r2

    def test_equivalent_specifiers_equal(self) -> None:
        # Two SpecifierSets that intersect to the same range should
        # produce equal VersionRanges.
        r1 = VersionRange.from_specifier_set(SpecifierSet(">=1.0,<2.0"))
        r2 = VersionRange.from_specifier_set(
            SpecifierSet(">=1.0") & SpecifierSet("<2.0")
        )
        assert r1 == r2

    def test_different_ranges_unequal(self) -> None:
        r1 = VersionRange.from_specifier_set(SpecifierSet(">=1.0"))
        r2 = VersionRange.from_specifier_set(SpecifierSet(">=2.0"))
        assert r1 != r2

    def test_compare_to_other_types(self) -> None:
        r = VersionRange.from_specifier_set(SpecifierSet(">=1.0"))
        assert r != "VersionRange"
        assert r != 42
        assert r != None  # noqa: E711

    def test_hash_matches_equality(self) -> None:
        r1 = VersionRange.from_specifier_set(SpecifierSet(">=1.0,<2.0"))
        r2 = VersionRange.from_specifier_set(SpecifierSet(">=1.0,<2.0"))
        assert hash(r1) == hash(r2)

    def test_hashable_in_set(self) -> None:
        r1 = VersionRange.from_specifier_set(SpecifierSet(">=1.0,<2.0"))
        r2 = VersionRange.from_specifier_set(SpecifierSet(">=1.0,<2.0"))
        r3 = VersionRange.from_specifier_set(SpecifierSet(">=3.0"))
        assert len({r1, r2, r3}) == 2


class TestRepr:
    @pytest.mark.parametrize(
        ("spec", "expected"),
        [
            (">=1.0,<2.0", "<VersionRange '[1.0, 2.0.dev0)'>"),
            (">=2.0,<1.0", "<VersionRange '(empty)'>"),
            ("", "<VersionRange '(-inf, +inf)'>"),
        ],
    )
    def test_repr_simple(self, spec: str, expected: str) -> None:
        assert repr(VersionRange.from_specifier_set(SpecifierSet(spec))) == expected

    def test_repr_disjoint(self) -> None:
        r = VersionRange.from_specifier_set(SpecifierSet("!=1.0"))
        assert " | " in repr(r)
        assert "(-inf" in repr(r)
        assert "+inf)" in repr(r)

    def test_repr_with_boundary(self) -> None:
        # AFTER_LOCALS / AFTER_POSTS bounds still produce a valid repr.
        r = VersionRange.from_specifier_set(SpecifierSet("<=1.0"))
        text = repr(r)
        assert text.startswith("<VersionRange")
        assert "1.0" in text


class TestPickle:
    def test_pickle_round_trip(self) -> None:
        r = VersionRange.from_specifier_set(SpecifierSet(">=1.0,<2.0"))
        restored = pickle.loads(pickle.dumps(r))
        assert restored == r
        assert "1.5" in restored
        assert "2.5" not in restored

    def test_pickle_empty_range(self) -> None:
        r = VersionRange.from_specifier_set(SpecifierSet(">=2.0,<1.0"))
        restored = pickle.loads(pickle.dumps(r))
        assert restored == r
        assert restored.is_empty

    def test_pickle_full_range(self) -> None:
        r = VersionRange.from_specifier_set(SpecifierSet(""))
        restored = pickle.loads(pickle.dumps(r))
        assert restored == r
        assert "1.0" in restored

    def test_pickle_disjoint(self) -> None:
        r = VersionRange.from_specifier_set(SpecifierSet("!=1.5"))
        restored = pickle.loads(pickle.dumps(r))
        assert restored == r
        assert "1.5" not in restored
        assert "1.6" in restored

    def test_pickle_at_all_protocols(self) -> None:
        r = VersionRange.from_specifier_set(SpecifierSet(">=1.0,<2.0"))
        for protocol in range(pickle.HIGHEST_PROTOCOL + 1):
            restored = pickle.loads(pickle.dumps(r, protocol=protocol))
            assert restored == r


class TestBoundaryClosureEdgeCases:
    """Edge cases for the closure-based boundary checks.

    These exercise branches that fire when the parsed version's
    release tuple is shorter than the bound version's trimmed
    release: uncommon in real specifiers but reachable.
    """

    def test_after_posts_short_release_above(self) -> None:
        # ``2`` has cmpkey > V but len(release)=1 < len(v_trimmed)=4.
        r = VersionRange.from_specifier_set(SpecifierSet(">1.0.0.5"))
        assert "2" in r
        assert "1" not in r
        assert "1.0.0.5" not in r

    def test_after_locals_short_release_below(self) -> None:
        # ``2`` has cmpkey > V but shorter release, so it cannot be
        # in V's local family.
        r = VersionRange.from_specifier_set(SpecifierSet("<=1.0.0.5"))
        assert "1" in r
        assert "1.0.0.5" in r
        assert "1.0.0.5+local" in r
        assert "2" not in r

    def test_after_locals_lower_short_release(self) -> None:
        # ``!=1.0.0.5`` puts an AFTER_LOCALS lower bound on the second
        # range; short-release versions must still resolve.
        r = VersionRange.from_specifier_set(SpecifierSet("!=1.0.0.5"))
        assert "2" in r
        assert "1" in r
        assert "1.0.0.5" not in r


class TestBoundaryVersionCompare:
    """The :class:`BoundaryVersion` class is private but its comparison
    operators must stay correct for the bound-sorting machinery."""

    @pytest.mark.parametrize(
        "version",
        [
            Version("1"),
            Version("1.0.dev1"),
            Version("1.0a1"),
            Version("1.0.post1"),
            Version("1.0+local"),
            Version("1.0.post1.dev2"),
        ],
    )
    def test_cmpkey_prefix_matches_version(self, version: Version) -> None:
        assert version_cmpkey(version) == version._key[:3]

    def test_lt_same_version_different_kind(self) -> None:
        # AFTER_LOCALS sorts before AFTER_POSTS for the same V.
        v = Version("1.0")
        a = BoundaryVersion(v, BoundaryKind.AFTER_LOCALS)
        b = BoundaryVersion(v, BoundaryKind.AFTER_POSTS)
        assert a < b
        assert not (b < a)

    def test_gt_same_version_different_kind(self) -> None:
        v = Version("1.0")
        a = BoundaryVersion(v, BoundaryKind.AFTER_LOCALS)
        b = BoundaryVersion(v, BoundaryKind.AFTER_POSTS)
        assert b > a
        assert not (a > b)

    def test_lt_different_versions(self) -> None:
        a = BoundaryVersion(Version("1.0"), BoundaryKind.AFTER_POSTS)
        b = BoundaryVersion(Version("2.0"), BoundaryKind.AFTER_POSTS)
        assert a < b


class TestEmptyFactory:
    """``VersionRange.empty`` builds the additive identity for union."""

    def test_returns_empty_range(self) -> None:
        r = VersionRange.empty()
        assert isinstance(r, VersionRange)
        assert r.is_empty
        assert not bool(r)

    def test_contains_nothing(self) -> None:
        r = VersionRange.empty()
        assert "1.0" not in r
        assert Version("1.0") not in r
        assert "0" not in r

    def test_intersect_with_empty_is_empty(self) -> None:
        any_r = VersionRange.full()
        e = VersionRange.empty()
        assert any_r.intersection(e).is_empty
        assert e.intersection(any_r).is_empty

    def test_union_with_empty_is_self(self) -> None:
        a = VersionRange.from_specifier(Specifier(">=1.0"))
        e = VersionRange.empty()
        assert a.union(e) == a
        assert e.union(a) == a

    def test_complement_of_empty_is_unbounded(self) -> None:
        assert VersionRange.empty().complement() == VersionRange.full()

    def test_equal_across_constructions(self) -> None:
        a = VersionRange.empty()
        b = VersionRange.from_specifier_set(SpecifierSet(">=2,<1"))
        assert a == b
        assert hash(a) == hash(b)


class TestUnboundedFactory:
    """``VersionRange.full`` builds the multiplicative identity for intersect."""

    def test_returns_full_range(self) -> None:
        r = VersionRange.full()
        assert isinstance(r, VersionRange)
        assert not r.is_empty
        assert bool(r)

    def test_contains_anything(self) -> None:
        # Full-range carve-out: admits arbitrary strings to match the
        # behaviour of ``SpecifierSet("")``.  Non-full ranges still
        # reject unparsable inputs.
        r = VersionRange.full()
        assert "0" in r
        assert "999.999.999" in r
        assert "1.0a1" in r
        assert "not-a-version" in r

    def test_intersect_with_unbounded_is_self(self) -> None:
        a = VersionRange.from_specifier_set(SpecifierSet(">=1.0,<2.0"))
        u = VersionRange.full()
        assert a.intersection(u) == a
        assert u.intersection(a) == a

    def test_union_with_unbounded_is_unbounded(self) -> None:
        a = VersionRange.from_specifier(Specifier(">=1.0"))
        u = VersionRange.full()
        assert a.union(u) == u
        assert u.union(a) == u

    def test_complement_of_unbounded_is_empty(self) -> None:
        assert VersionRange.full().complement().is_empty

    def test_equal_to_empty_specifier_set(self) -> None:
        assert VersionRange.full() == VersionRange.from_specifier_set(SpecifierSet(""))


class TestExactFactory:
    """``VersionRange.singleton`` builds the singleton range."""

    @pytest.mark.parametrize("arg", ["1.2.3", Version("1.2.3")])
    def test_from_string_or_version(self, arg: str | Version) -> None:
        r = VersionRange.singleton(arg)
        assert "1.2.3" in r
        assert "1.2.4" not in r
        assert "1.2.2" not in r

    def test_invalid_string_raises(self) -> None:
        from packaging.version import InvalidVersion  # noqa: PLC0415

        with pytest.raises(InvalidVersion):
            VersionRange.singleton("not-a-version")

    def test_equal_to_eq_specifier(self) -> None:
        # ``==1.2.3`` matches ``1.2.3`` and ``1.2.3+local``; ``exact``
        # is the strict singleton, not the same range.
        exact = VersionRange.singleton("1.2.3")
        eq_spec = VersionRange.from_specifier(Specifier("==1.2.3"))
        assert "1.2.3+local" in eq_spec
        assert "1.2.3+local" not in exact

    def test_intersect_disjoint_exacts_is_empty(self) -> None:
        a = VersionRange.singleton("1.0")
        b = VersionRange.singleton("2.0")
        assert a.intersection(b).is_empty

    def test_intersect_equal_exacts_is_self(self) -> None:
        a = VersionRange.singleton("1.0")
        b = VersionRange.singleton("1.0")
        assert a.intersection(b) == a

    def test_hashable(self) -> None:
        a = VersionRange.singleton("1.0")
        b = VersionRange.singleton("1.0")
        assert hash(a) == hash(b)
        assert len({a, b, VersionRange.singleton("2.0")}) == 2


class TestUnion:
    def test_disjoint_exacts(self) -> None:
        a = VersionRange.singleton("1.0")
        b = VersionRange.singleton("2.0")
        u = a.union(b)
        assert "1.0" in u
        assert "2.0" in u
        assert "1.5" not in u

    def test_overlapping_intervals_collapse(self) -> None:
        a = VersionRange.from_specifier_set(SpecifierSet(">=1.0,<2.0"))
        b = VersionRange.from_specifier_set(SpecifierSet(">=1.5,<3.0"))
        u = a.union(b)
        assert "1.0" in u
        assert "2.5" in u
        assert "3.0" not in u
        assert "0.5" not in u

    def test_union_with_self_is_self(self) -> None:
        a = VersionRange.from_specifier(Specifier(">=1.0"))
        assert a.union(a) == a

    def test_union_of_neg_complementary_ranges_covers_all(self) -> None:
        lower = VersionRange.from_specifier(Specifier("<1.0"))
        upper = VersionRange.from_specifier(Specifier(">=1.0"))
        u = lower.union(upper)
        assert "0.5" in u
        assert "1.0" in u
        assert "999" in u

    def test_union_preserves_disjoint_repr_count(self) -> None:
        a = VersionRange.singleton("1.0")
        b = VersionRange.singleton("3.0")
        u = a.union(b)
        assert " | " in repr(u)

    def test_union_of_two_unbounded_lower_collapses(self) -> None:
        a = VersionRange.from_specifier(Specifier("<1"))
        b = VersionRange.from_specifier(Specifier("<2"))
        assert a.union(b) == b

    def test_disjoint_post_boundary_not_bridged(self) -> None:
        # >1.0 excludes posts of 1.0, so 1.0.post1 is in neither operand.
        a = VersionRange.from_specifier(Specifier("==1.0.post0"))
        b = VersionRange.from_specifier(Specifier(">1.0"))
        u = a.union(b)
        assert Version("1.0.post0") in u
        assert Version("1.0.post1") not in u
        assert Version("1.1") in u

    def test_union_of_two_unbounded_upper_collapses(self) -> None:
        a = VersionRange.from_specifier(Specifier(">=1"))
        b = VersionRange.from_specifier(Specifier(">=2"))
        assert a.union(b) == a

    def test_touching_inclusive_exclusive_collapses(self) -> None:
        # [1.0, 2.0) U [2.0, 3.0) == [1.0, 3.0)
        a = VersionRange.from_specifier_set(SpecifierSet(">=1.0,<2.0"))
        b = VersionRange.from_specifier_set(SpecifierSet(">=2.0,<3.0"))
        u = a.union(b)
        assert "1.5" in u
        assert "2.0" in u
        assert "2.999" in u
        assert "3.0" not in u

    def test_touching_exclusive_exclusive_does_not_collapse(self) -> None:
        # [1.0, 2.0) U (2.0, 3.0) still excludes 2.0
        a = VersionRange.from_specifier_set(SpecifierSet(">=1.0,<2.0"))
        b = VersionRange.from_specifier_set(SpecifierSet(">2.0,<3.0"))
        u = a.union(b)
        assert "2.0" not in u
        assert "1.5" in u
        assert "2.5" in u

    def test_touching_inclusive_inclusive_at_same_version_collapses(self) -> None:
        # Two singletons at the same Version both have inclusive bounds
        # at that Version; the union collapses to a single singleton.
        a = VersionRange.singleton("1.0")
        b = VersionRange.singleton("1.0")
        assert a.union(b) == a


class TestComplement:
    @pytest.mark.parametrize(
        ("spec", "members", "non_members"),
        [
            (">=2.0", ["1.0"], ["2.0", "3.0"]),
            ("<2.0", ["2.0", "3.0"], ["1.0"]),
            # ~(!=V) is {V}.
            ("!=1.5", ["1.5"], ["1.4", "1.6"]),
        ],
    )
    def test_complement_of_simple_specifier(
        self, spec: str, members: list[str], non_members: list[str]
    ) -> None:
        r = VersionRange.from_specifier(Specifier(spec))
        c = r.complement()
        for v in members:
            assert v in c
        for v in non_members:
            assert v not in c

    def test_complement_creates_after_posts_upper_bound(self) -> None:
        # Complementing an AFTER_POSTS lower bound exercises every
        # branch of the upper-side post-family predicate.
        r = VersionRange.from_specifier_set(SpecifierSet(">1.0,<=2.0"))
        c = r.complement()
        assert "1.0" in c
        assert "1.0+local" in c
        assert "1.0.post0" in c
        assert "1.0.post5+local" in c
        assert "1.5" not in c
        # Isolated AFTER_POSTS complement: covers shorter-release path.
        r2 = VersionRange.from_specifier_set(SpecifierSet(">1.0.0.5"))
        c2 = r2.complement()
        assert "1.0.0.5" in c2
        assert "1.0.0.5.post0" in c2
        # ``2`` has release shorter than v's trimmed (1,0,0,5).
        assert "2" not in c2
        assert "1.0.0.6" not in c2
        # Tail-zero release matches the family.
        r3 = VersionRange.from_specifier_set(SpecifierSet(">1.0"))
        c3 = r3.complement()
        assert "1.0.0" in c3
        assert "1.0.0.post0" in c3
        assert "1.0.1" not in c3
        # Pre-release mismatch path.
        r4 = VersionRange.from_specifier_set(SpecifierSet(">1.0a1"))
        c4 = r4.complement()
        assert "1.0a2" not in c4
        # Different epoch path.
        assert "2!1.0" not in c3


class TestOperatorAliases:
    def test_and_aliases_intersect(self) -> None:
        a = VersionRange.from_specifier(Specifier(">=1.0"))
        b = VersionRange.from_specifier(Specifier("<2.0"))
        assert (a & b) == a.intersection(b)

    def test_or_aliases_union(self) -> None:
        a = VersionRange.singleton("1.0")
        b = VersionRange.singleton("2.0")
        assert (a | b) == a.union(b)

    def test_invert_aliases_complement(self) -> None:
        r = VersionRange.from_specifier(Specifier(">=1.0"))
        assert (~r) == r.complement()

    def test_and_with_non_range_returns_notimplemented(self) -> None:
        a = VersionRange.from_specifier(Specifier(">=1.0"))
        with pytest.raises(TypeError):
            a & "not a range"
        with pytest.raises(TypeError):
            a & 42

    def test_or_with_non_range_returns_notimplemented(self) -> None:
        a = VersionRange.from_specifier(Specifier(">=1.0"))
        with pytest.raises(TypeError):
            a | "not a range"
        with pytest.raises(TypeError):
            a | 42

    def test_chained_operations(self) -> None:
        # ``(>=1) & (<2) | (==3)``
        ge1 = VersionRange.from_specifier(Specifier(">=1.0"))
        lt2 = VersionRange.from_specifier(Specifier("<2.0"))
        eq3 = VersionRange.singleton("3.0")
        result = (ge1 & lt2) | eq3
        assert "1.5" in result
        assert "3.0" in result
        assert "2.5" not in result


class TestToSpecifierSet:
    """``to_specifier_set`` returns a single SpecifierSet or ``None``."""

    def test_full_range_round_trips_via_empty_specifier_set(self) -> None:
        assert VersionRange.full().to_specifier_set() == SpecifierSet("")

    def test_empty_range_round_trips_via_lt_zero(self) -> None:
        # ``<0`` is the canonical empty SpecifierSet (0.dev0 is the
        # smallest PEP 440 version).
        assert VersionRange.empty().to_specifier_set() == SpecifierSet("<0")
        assert (
            VersionRange.from_specifier_set(SpecifierSet("<0")) == VersionRange.empty()
        )

    def test_singleton_returns_none_for_local_less_version(self) -> None:
        # ``==V`` matches V+local, so the strict ``[V, V]`` singleton
        # has no SpecifierSet form.
        assert VersionRange.singleton("1.5").to_specifier_set() is None

    def test_singleton_with_local_round_trips_via_eq(self) -> None:
        r = VersionRange.singleton("1.5+local")
        ss = r.to_specifier_set()
        assert ss is not None
        assert VersionRange.from_specifier_set(ss) == r

    def test_complement_of_half_line_round_trips_via_le_ne_pair(self) -> None:
        # ``~(>=1.0)`` round-trips as ``<=1.0,!=1.0``.
        ge1 = VersionRange.from_specifier(Specifier(">=1.0"))
        ss = ge1.complement().to_specifier_set()
        assert ss is not None
        assert VersionRange.from_specifier_set(ss) == ge1.complement()

    def test_complement_of_strict_greater_than_returns_none(self) -> None:
        # ``~(>V)`` produces an inclusive AFTER_POSTS upper bound,
        # which has no specifier representation.
        gt1 = VersionRange.from_specifier(Specifier(">1.0"))
        assert gt1.complement().to_specifier_set() is None

    def test_strict_greater_than_round_trips_via_gt(self) -> None:
        # ``>V`` has an AFTER_POSTS lower bound; round-trips as ``>V``.
        r = VersionRange.from_specifier(Specifier(">1.0"))
        assert r.to_specifier_set() == SpecifierSet(">1.0")

    def test_complement_of_le_round_trips_via_ne_ge_pair(self) -> None:
        # ``~(<=V)`` has an AFTER_LOCALS lower bound; round-trips as
        # ``>=V,!=V`` (excludes V and every V+local).
        le1 = VersionRange.from_specifier(Specifier("<=1.0"))
        comp = le1.complement()
        assert comp.to_specifier_set() == SpecifierSet(">=1.0,!=1.0")

    def test_disjoint_union_returns_none_when_gap_unaligned(self) -> None:
        # The gap between ``[1.0, 2.0)`` and ``[3.0, 4.0)`` does not
        # align with any ``==V.*`` family.
        a = VersionRange.from_specifier_set(SpecifierSet(">=1.0,<2.0"))
        b = VersionRange.from_specifier_set(SpecifierSet(">=3.0,<4.0"))
        assert (a | b).to_specifier_set() is None

    def test_after_locals_upper_then_plain_lower_returns_none(self) -> None:
        # AFTER_LOCALS upper + plain lower fails ``!=V``/``!=V.*``
        # detection (left bound shape check), but the per-interval
        # tuple form still succeeds.
        r = VersionRange.from_specifier(
            Specifier("<=1.0")
        ) | VersionRange.from_specifier(Specifier(">=2.0"))
        assert r.to_specifier_set() is None
        sets = r.to_specifier_sets()
        assert sets is not None
        assert len(sets) == 2

    def test_lt_excl_then_ge_incl_returns_none_on_unaligned_gap(self) -> None:
        # Both ``!=V`` and ``!=V.*`` detection require matching bound
        # shapes that this gap does not satisfy.
        r = VersionRange.from_specifier(
            Specifier("<1.0")
        ) | VersionRange.from_specifier(Specifier(">=3.0"))
        assert r.to_specifier_set() is None

    def test_unaligned_dev0_release_lengths_returns_none(self) -> None:
        # Both bounds are X.dev0 but release lengths differ, so
        # ``!=V.*`` does not apply.
        a = VersionRange.from_specifier(Specifier("<1.dev0"))
        b = VersionRange.from_specifier_set(SpecifierSet(">=1.2.dev0"))
        u = a | b
        assert u.to_specifier_set() is None

    def test_unaligned_dev0_increment_round_trips(self) -> None:
        # ``==1.* | ==3.*`` canonicalises to a gap of width 1 between
        # 2.dev0 and 3.dev0, so ``!=2.*`` IS expressible. Confirm the
        # round-trip (positive path of the increment check).
        a = VersionRange.from_specifier(Specifier("==1.*"))
        b = VersionRange.from_specifier(Specifier("==3.*"))
        u = a | b
        ss = u.to_specifier_set()
        assert ss is not None
        assert VersionRange.from_specifier_set(ss) == u

    def test_unaligned_release_prefix_returns_none(self) -> None:
        # Same release length but the prefix doesn't match the increment
        # pattern ``!=V.*`` requires, so the gap is not expressible as a
        # single specifier set.
        a = VersionRange.from_specifier(Specifier("<1.0.dev0"))
        b = VersionRange.from_specifier_set(SpecifierSet(">=2.0.dev0"))
        u = a | b
        assert u.to_specifier_set() is None

    def test_v_exclusive_lower_bound_is_not_encodable(self) -> None:
        # ``~singleton(V)`` produces two ``V (excl)`` bounds. The
        # second interval's V-exclusive lower has no specifier form.
        s = VersionRange.singleton("1.5")
        c = s.complement()
        assert c.to_specifier_set() is None
        assert c.to_specifier_sets() is None

    def test_after_posts_lower_after_plain_upper_breaks_ne_v(self) -> None:
        # AFTER_POSTS right lower fails the right-bound shape check
        # in both ``!=V`` and ``!=V.*`` detection.
        a = VersionRange.from_specifier(Specifier("<1.0"))
        b = VersionRange.from_specifier(Specifier(">2.0"))
        u = a | b
        assert u.to_specifier_set() is None

    def test_disjoint_singletons_break_ne_v_star_at_inclusive_left(self) -> None:
        # Inclusive left upper bails the ``!=V.*`` guard, and
        # singletons aren't specifier-shaped per-interval either.
        u = VersionRange.singleton("1.0") | VersionRange.singleton("2.0")
        assert u.to_specifier_set() is None

    def test_far_apart_dev0_release_breaks_ne_v_star_increment(self) -> None:
        # Gap of width 4 fails the ``!=V.*`` increment check.
        a = VersionRange.from_specifier(Specifier("==1.*"))
        b = VersionRange.from_specifier(Specifier("==5.*"))
        u = a | b
        assert u.to_specifier_set() is None


class TestToSpecifierSets:
    """``to_specifier_sets`` returns a tuple of SpecifierSets, or ``None``."""

    def test_full_range_returns_one_tuple_of_empty_specifier_set(self) -> None:
        assert VersionRange.full().to_specifier_sets() == (SpecifierSet(""),)

    def test_empty_range_returns_lt_zero_tuple(self) -> None:
        assert VersionRange.empty().to_specifier_sets() == (SpecifierSet("<0"),)

    def test_singleton_returns_none(self) -> None:
        # Per-interval encoding of [V, V] also fails: the inclusive
        # upper bound has no specifier.
        assert VersionRange.singleton("1.5").to_specifier_sets() is None

    def test_disjoint_union_succeeds_with_one_set_per_interval(self) -> None:
        a = VersionRange.from_specifier_set(SpecifierSet(">=1.0,<2.0"))
        b = VersionRange.from_specifier_set(SpecifierSet(">=3.0,<4.0"))
        union = a | b
        sets = union.to_specifier_sets()
        assert sets is not None
        assert len(sets) == 2
        left = VersionRange.from_specifier_set(sets[0])
        right = VersionRange.from_specifier_set(sets[1])
        assert (left | right) == union

    def test_multi_interval_range_with_single_set_form_returns_one_tuple(
        self,
    ) -> None:
        # ``!=1.0`` has a single-set form, so the tuple is length 1
        # instead of falling through to per-interval encoding.
        r = VersionRange.from_specifier(Specifier("!=1.0"))
        sets = r.to_specifier_sets()
        assert sets == (SpecifierSet("!=1.0"),)

    def test_cross_epoch_union_breaks_ne_v_star_epoch_check(self) -> None:
        # ``!=V.*`` detection bails at the epoch equality check.
        a = VersionRange.from_specifier(Specifier("==1.*"))
        b = VersionRange.from_specifier(Specifier("==1!1.*"))
        u = a | b
        assert u.to_specifier_set() is None

    def test_local_not_equal_round_trips(self) -> None:
        # ``!=1.0+foo`` excludes exactly the single local version
        # ``1.0+foo`` (a single-point gap), so it round-trips through a
        # single SpecifierSet rather than raising ``InvalidSpecifier``.
        r = VersionRange.from_specifier(Specifier("!=1.0+foo"))
        assert r.to_specifier_set() == SpecifierSet("!=1.0+foo")
        assert r.to_specifier_sets() == (SpecifierSet("!=1.0+foo"),)

    def test_disjoint_groups_keep_internal_not_equal_merged(self) -> None:
        # Two disjoint runs, each with an internal ``!=`` gap, stay
        # merged within their own group instead of splitting per interval.
        r = VersionRange.from_specifier_set(
            SpecifierSet(">=1.0,<2.0,!=1.5")
        ) | VersionRange.from_specifier_set(SpecifierSet(">=5.0,<6.0,!=5.5"))
        sets = r.to_specifier_sets()
        assert sets is not None
        assert [str(s) for s in sets] == ["!=1.5,<2.0,>=1.0", "!=5.5,<6.0,>=5.0"]
        union = VersionRange.empty()
        for s in sets:
            union = union | VersionRange.from_specifier_set(s)
        assert union == r

    def test_local_not_equal_in_disjoint_group_round_trips(self) -> None:
        # A ``!=V+local`` gap inside one disjoint run survives the split
        # (this raised InvalidSpecifier before the single-point gap fix).
        r = (
            VersionRange.from_specifier(Specifier("!=1.0+foo"))
            & VersionRange.from_specifier_set(SpecifierSet(">=1.0,<2.0"))
        ) | VersionRange.from_specifier_set(SpecifierSet(">=5.0"))
        sets = r.to_specifier_sets()
        assert sets is not None
        union = VersionRange.empty()
        for s in sets:
            union = union | VersionRange.from_specifier_set(s)
        assert union == r

    def test_unencodable_nonfinal_group_returns_none(self) -> None:
        # A strict singleton run ahead of a disjoint interval has no
        # PEP 440 form, so the whole conversion is None.
        r = VersionRange.singleton("1.5") | VersionRange.from_specifier_set(
            SpecifierSet(">=5.0")
        )
        assert r.to_specifier_sets() is None


class TestArbitraryCarveOut:
    """``===`` arbitrary-equality ranges: a case-insensitive string-match
    layered on top of a regular range."""

    def test_filter_with_explicit_prereleases_true(self) -> None:
        r = VersionRange.from_specifier(Specifier("===1.0a1"))
        items = ["1.0a1", "1.0", "1.0A1", "other"]
        assert list(r.filter(items, prereleases=True)) == ["1.0a1", "1.0A1"]

    def test_filter_with_explicit_prereleases_false_drops_prerelease(self) -> None:
        r = VersionRange.from_specifier(Specifier("===1.0a1"))
        # ``1.0a1`` parses as a pre-release; ``prereleases=False`` drops it.
        assert list(r.filter(["1.0a1"], prereleases=False)) == []

    def test_filter_with_explicit_prereleases_false_keeps_unparsable(self) -> None:
        # Unparsable strings can't be prerelease-filtered out (mirrors
        # ``Specifier.filter``).
        r = VersionRange.from_specifier(Specifier("===wat"))
        assert list(r.filter(["wat"], prereleases=False)) == ["wat"]

    def test_filter_default_pep440_buffers_unparsable_until_final(self) -> None:
        # No final ever arrives, so unparsable buffered items flush at end.
        r = VersionRange.from_specifier(Specifier("===wat"))
        assert list(r.filter(["wat", "WAT", "other"])) == ["wat", "WAT"]

    def test_filter_default_pep440_yields_unparsable_after_final(self) -> None:
        r = VersionRange.from_specifier(Specifier("===1.0"))
        assert list(r.filter(["1.0", "other", "1.0"])) == ["1.0", "1.0"]

    def test_filter_default_pep440_buffers_prereleases(self) -> None:
        r = VersionRange.from_specifier(Specifier("===1.0a1"))
        assert list(r.filter(["1.0a1", "other"])) == ["1.0a1"]

    def test_to_specifier_set_full_bounds(self) -> None:
        r = VersionRange.from_specifier(Specifier("===wat"))
        assert r.to_specifier_set() == SpecifierSet("===wat")

    def test_to_specifier_set_empty_bounds(self) -> None:
        # ``wat`` cannot satisfy ``>=1``, so the conjunction is empty
        # and the literal tag is dropped on round-trip.
        r = VersionRange.from_specifier_set(SpecifierSet("===wat,>=1"))
        ss = r.to_specifier_set()
        assert ss == SpecifierSet("<0")
        assert VersionRange.from_specifier_set(ss) == r

    def test_to_specifier_set_with_rangelike_lossy_round_trip(self) -> None:
        # The literal "1.5" parses inside [1.0, 2.0), so the rangelike
        # tail is redundant and gets dropped on round-trip.
        r = VersionRange.from_specifier_set(SpecifierSet("===1.5,>=1.0,<2.0"))
        ss = r.to_specifier_set()
        assert ss == SpecifierSet("===1.5")
        assert VersionRange.from_specifier_set(ss) == r

    def test_to_specifier_sets_returns_one_tuple(self) -> None:
        r = VersionRange.from_specifier(Specifier("===wat"))
        sets = r.to_specifier_sets()
        assert sets == (SpecifierSet("===wat"),)

    def test_repr_arbitrary_full(self) -> None:
        r = VersionRange.from_specifier(Specifier("===wat"))
        assert repr(r) == "<VersionRange '{wat}'>"

    def test_repr_arbitrary_empty(self) -> None:
        r = VersionRange.from_specifier_set(SpecifierSet("===wat,>=1"))
        assert repr(r) == "<VersionRange '(empty)'>"

    def test_repr_admit_with_bounds(self) -> None:
        wat = VersionRange.from_specifier(Specifier("===wat"))
        rangelike = VersionRange.from_specifier_set(SpecifierSet(">=1.0,<2.0"))
        r = wat.union(rangelike)
        assert repr(r) == "<VersionRange '[1.0, 2.0.dev0) | {wat}'>"

    def test_repr_reject(self) -> None:
        r = VersionRange.from_specifier(Specifier("===wat")).complement()
        assert repr(r) == "<VersionRange '(-inf, +inf) \\\\ {wat}'>"

    def test_eq_case_insensitive_arbitrary(self) -> None:
        a = VersionRange.from_specifier(Specifier("===WAT"))
        b = VersionRange.from_specifier(Specifier("===wat"))
        assert a == b
        assert hash(a) == hash(b)

    def test_eq_arbitrary_vs_non_arbitrary_distinct(self) -> None:
        a = VersionRange.from_specifier(Specifier("===wat"))
        b = VersionRange.full()
        assert a != b
        assert b != a

    def test_eq_two_different_arbitrary_literals_distinct(self) -> None:
        a = VersionRange.from_specifier(Specifier("===wat"))
        b = VersionRange.from_specifier(Specifier("===other"))
        assert a != b

    def test_contains_unparsable_string_matching_arbitrary(self) -> None:
        r = VersionRange.from_specifier(Specifier("===wat"))
        assert "wat" in r

    def test_pickle_round_trip_preserves_arbitrary(self) -> None:
        r = VersionRange.from_specifier(Specifier("===wat"))
        restored = pickle.loads(pickle.dumps(r))
        assert restored == r
        assert restored._admit == frozenset({"wat"})

    def test_arbitrary_full_bounds_is_satisfiable(self) -> None:
        r = VersionRange.from_specifier(Specifier("===wat"))
        assert not r.is_empty
        assert not SpecifierSet("===wat").is_unsatisfiable()
        assert not SpecifierSet("===wat", prereleases=True).is_unsatisfiable()

    def test_arbitrary_prerelease_unsatisfiable_with_no_pre(self) -> None:
        # Prerelease exclusion is enforced at the SpecifierSet layer;
        # the carve-out range still accepts the literal.
        r = VersionRange.from_specifier(Specifier("===1.0a1"))
        assert not r.is_empty
        assert SpecifierSet("===1.0a1", prereleases=False).is_unsatisfiable()
        assert not SpecifierSet("===1.0a1").is_unsatisfiable()

    def test_to_specifier_set_returns_none_for_lattice_shapes(self) -> None:
        # PEP 440 has no disjunction operator; admit-with-bounds and
        # non-empty reject sets are both unencodable.
        wat = VersionRange.from_specifier(Specifier("===wat"))
        rangelike = VersionRange.from_specifier_set(SpecifierSet(">=1.0,<2.0"))
        assert wat.union(rangelike).to_specifier_set() is None
        assert wat.complement().to_specifier_set() is None


class TestArbitraryLatticeOps:
    """Lattice operations on ``===``-derived ranges."""

    def test_intersection_two_same_literal(self) -> None:
        a = VersionRange.from_specifier(Specifier("===wat"))
        b = VersionRange.from_specifier(Specifier("===WAT"))
        assert a.intersection(b) == a

    def test_intersection_two_distinct_literals_is_empty(self) -> None:
        a = VersionRange.from_specifier(Specifier("===wat"))
        b = VersionRange.from_specifier(Specifier("===other"))
        result = a.intersection(b)
        assert result.is_empty
        assert result._admit == frozenset()

    def test_intersection_with_disjoint_rangelike_drops_literal(self) -> None:
        arb = VersionRange.from_specifier(Specifier("===1.5"))
        rangelike = VersionRange.from_specifier_set(SpecifierSet(">=10"))
        assert arb.intersection(rangelike).is_empty

    def test_intersection_unparsable_literal_with_rangelike(self) -> None:
        wat = VersionRange.from_specifier(Specifier("===wat"))
        rangelike = VersionRange.from_specifier_set(SpecifierSet(">=1.0"))
        result = wat.intersection(rangelike)
        assert result.is_empty
        assert "wat" not in result

    def test_union_of_distinct_literals(self) -> None:
        a = VersionRange.from_specifier(Specifier("===wat"))
        b = VersionRange.from_specifier(Specifier("===other"))
        result = a.union(b)
        assert "wat" in result
        assert "other" in result
        assert "third" not in result
        assert result._admit == frozenset({"wat", "other"})

    def test_union_admit_with_rangelike_drops_redundant_admit(self) -> None:
        # The admit literal is already in the bounds.
        arb = VersionRange.from_specifier(Specifier("===1.5"))
        rangelike = VersionRange.from_specifier_set(SpecifierSet(">=1.0,<2.0"))
        result = arb.union(rangelike)
        assert result._admit == frozenset()
        assert result == rangelike

    def test_union_admit_with_disjoint_rangelike_keeps_admit(self) -> None:
        arb = VersionRange.from_specifier(Specifier("===1.5"))
        rangelike = VersionRange.from_specifier_set(SpecifierSet(">=10"))
        result = arb.union(rangelike)
        assert result._admit == frozenset({"1.5"})
        assert "1.5" in result
        assert "10.0" in result
        assert "5.0" not in result

    def test_complement_of_admit_swaps_to_reject(self) -> None:
        wat = VersionRange.from_specifier(Specifier("===wat"))
        comp = wat.complement()
        assert comp._admit == frozenset()
        assert comp._reject == frozenset({"wat"})
        assert "wat" not in comp
        assert "1.0" in comp
        assert comp.complement() == wat

    def test_complement_of_reject_swaps_to_admit(self) -> None:
        wat = VersionRange.from_specifier(Specifier("===wat"))
        assert wat.complement().complement() == wat

    def test_intersection_admit_with_reject_is_empty(self) -> None:
        wat = VersionRange.from_specifier(Specifier("===wat"))
        not_wat = wat.complement()
        result = wat.intersection(not_wat)
        assert result.is_empty
        assert result._admit == frozenset()
        assert result._reject == frozenset()

    def test_partition_law_for_arbitrary(self) -> None:
        wat = VersionRange.from_specifier(Specifier("===wat"))
        comp = wat.complement()
        assert wat.union(comp) == VersionRange.full()
        assert wat.intersection(comp) == VersionRange.empty()

    def test_intersection_drops_redundant_reject(self) -> None:
        # ``>=1.0`` does not contain "wat" anyway.
        not_wat = VersionRange.from_specifier(Specifier("===wat")).complement()
        rangelike = VersionRange.from_specifier_set(SpecifierSet(">=1.0"))
        result = not_wat.intersection(rangelike)
        assert result._reject == frozenset()
        assert result == rangelike

    def test_union_then_intersect_resolves_each_literal(self) -> None:
        # 1.5 survives the rangelike intersection; "wat" does not.
        a = VersionRange.from_specifier(Specifier("===1.5"))
        b = VersionRange.from_specifier(Specifier("===wat"))
        rangelike = VersionRange.from_specifier_set(SpecifierSet(">=1.0,<2.0"))
        result = a.union(b).intersection(rangelike)
        assert "1.5" in result
        assert "wat" not in result
        assert "1.7" not in result

    def test_pickle_round_trip_preserves_reject(self) -> None:
        wat = VersionRange.from_specifier(Specifier("===wat"))
        comp = wat.complement()
        restored = pickle.loads(pickle.dumps(comp))
        assert restored == comp
        assert restored._reject == frozenset({"wat"})


class TestPickleBackwardCompat:
    """Loading pickles written before the admit/reject change."""

    def test_legacy_arbitrary_with_full_bounds_loads_to_admit(self) -> None:
        # Legacy ``_arbitrary='wat', _bounds=FULL_RANGE`` migrates to
        # ``_admit={"wat"}, _bounds=()``.
        full = VersionRange.full()
        packed_bounds = tuple(
            (
                (
                    None if lower.version is None else str(lower.version),
                    lower.inclusive,
                    None,
                ),
                (
                    None if upper.version is None else str(upper.version),
                    upper.inclusive,
                    None,
                ),
            )
            for lower, upper in full._bounds
        )
        restored = _restore_version_range(packed_bounds, "wat")
        assert restored._admit == frozenset({"wat"})
        assert "wat" in restored

    def test_legacy_arbitrary_with_disjoint_bounds_loads_to_empty(self) -> None:
        # Disjoint legacy state: literal tag is dropped on load.
        restored = _restore_version_range((), "wat")
        assert restored.is_empty
        assert restored._admit == frozenset()

    def test_legacy_no_arbitrary_loads_unchanged(self) -> None:
        restored = _restore_version_range((), None)
        assert restored == VersionRange.empty()


class TestArbitraryEdgeCases:
    """Admit/reject canonicalization and filter paths."""

    def test_build_drops_admit_reject_overlap(self) -> None:
        r = VersionRange._build((), admit=frozenset({"wat"}), reject=frozenset({"wat"}))
        assert "wat" not in r
        assert r._admit == frozenset()
        assert r._reject == frozenset()

    def test_intersection_produces_reject_inside_bounds(self) -> None:
        # The reject keeps "1.0" out even though the bounds admit it.
        not_one = VersionRange.from_specifier(Specifier("===1.0")).complement()
        eq_one = VersionRange.from_specifier(Specifier("==1.0"))
        result = not_one.intersection(eq_one)
        assert "1.0" not in result
        assert "1.0+local" in result
        assert result._reject == frozenset({"1.0"})

    def test_filter_rejects_explicit_literal(self) -> None:
        not_wat = VersionRange.from_specifier(Specifier("===wat")).complement()
        assert list(not_wat.filter(["wat", "WAT", "1.0"])) == ["1.0"]

    def test_to_specifier_sets_reject_returns_none(self) -> None:
        not_wat = VersionRange.from_specifier(Specifier("===wat")).complement()
        assert not_wat.to_specifier_sets() is None

    def test_to_specifier_sets_multiple_admit_returns_none(self) -> None:
        # PEP 440 has no syntax for OR over distinct ``===`` literals.
        a = VersionRange.from_specifier(Specifier("===wat"))
        b = VersionRange.from_specifier(Specifier("===other"))
        assert a.union(b).to_specifier_sets() is None

    def test_is_prerelease_only_empty_is_false(self) -> None:
        assert VersionRange.empty().is_prerelease_only is False

    def test_is_prerelease_only_with_reject_is_false(self) -> None:
        not_wat = VersionRange.from_specifier(Specifier("===wat")).complement()
        assert not_wat.is_prerelease_only is False

    def test_is_prerelease_only_with_unparsable_admit(self) -> None:
        # An unparsable literal isn't a Version, so it's not a pre-release.
        wat = VersionRange.from_specifier(Specifier("===wat"))
        assert wat.is_prerelease_only is False

    def test_is_prerelease_only_with_prerelease_admit_only(self) -> None:
        pre = VersionRange.from_specifier(Specifier("===1.0a1"))
        assert pre.is_prerelease_only is True

    def test_is_prerelease_only_with_final_admit_only(self) -> None:
        final = VersionRange.from_specifier(Specifier("===1.0"))
        assert final.is_prerelease_only is False

    def test_is_prerelease_only_admit_with_prerelease_bounds(self) -> None:
        admit_pre = VersionRange.from_specifier(Specifier("===1.0a1"))
        bounds_pre = VersionRange.from_specifier_set(SpecifierSet(">=1.0a1,<1.0"))
        assert admit_pre.union(bounds_pre).is_prerelease_only is True


class TestPrereleaseComposition:
    """Set algebra must carry pre-release eligibility, so a composed range
    filters like the composed specifier. A single ``to_range`` conversion is
    already faithful; ``&`` / ``|`` must not drop the tag (``~`` may reset it).
    """

    # A final release and a pre-release; both sit inside every range below.
    SAMPLE_VERSIONS = (Version("1.0"), Version("2.0a1"))

    @staticmethod
    def _tagged_ranges() -> tuple[VersionRange, VersionRange, VersionRange]:
        """Three ranges that contain both SAMPLE_VERSIONS, one per resolved
        tag: auto-detected True, PEP 440 default None, and explicit False."""
        true_tag = SpecifierSet(">=1.0a1").to_range()
        none_tag = SpecifierSet("<3.0").to_range()
        false_tag = SpecifierSet("<3.0", prereleases=False).to_range()
        assert true_tag._prereleases is True
        assert none_tag._prereleases is None
        assert false_tag._prereleases is False
        return true_tag, none_tag, false_tag

    def test_full_range_is_identity_for_filtering(self) -> None:
        full = VersionRange.full()
        for r in self._tagged_ranges():
            expected = list(r.filter(self.SAMPLE_VERSIONS))
            assert list((r & full).filter(self.SAMPLE_VERSIONS)) == expected
            assert list((full & r).filter(self.SAMPLE_VERSIONS)) == expected

    def test_intersection_combines_true_then_false_then_none(self) -> None:
        true_tag, none_tag, false_tag = self._tagged_ranges()
        assert (true_tag & none_tag)._prereleases is True  # True dominates
        assert (true_tag & false_tag)._prereleases is True
        assert (false_tag & none_tag)._prereleases is False  # then False
        assert (none_tag & none_tag)._prereleases is None  # else None
        assert (true_tag & true_tag)._prereleases is True

    def test_union_combines_true_then_false_then_none(self) -> None:
        true_tag, none_tag, false_tag = self._tagged_ranges()
        assert (true_tag | none_tag)._prereleases is True
        assert (true_tag | false_tag)._prereleases is True
        assert (false_tag | none_tag)._prereleases is False
        assert (none_tag | none_tag)._prereleases is None

    def test_complement_resets_tag_to_none(self) -> None:
        for r in self._tagged_ranges():
            assert r.complement()._prereleases is None

    @pytest.mark.parametrize(
        ("s1", "s2"),
        [
            (">=1.0a1", "<3.0"),
            (">=1.0", "<3.0"),
            (">=1.0a1", ">=1.0a1"),
            (">=1.0a1,<3.0", ""),
            ("", ">=1.0a1"),
            (">=1.0", ">=1.0a1"),
        ],
    )
    def test_intersection_is_a_homomorphism(self, s1: str, s2: str) -> None:
        """``(a.to_range() & b.to_range()).filter`` equals
        ``(a & b).to_range().filter``."""
        a, b = SpecifierSet(s1), SpecifierSet(s2)
        composed_ranges = list(
            (a.to_range() & b.to_range()).filter(self.SAMPLE_VERSIONS)
        )
        composed_set = list((a & b).to_range().filter(self.SAMPLE_VERSIONS))
        assert composed_ranges == composed_set
