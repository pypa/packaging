# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.

from __future__ import annotations

import copy
import pickle
import sys
from dataclasses import dataclass
from typing import ClassVar

import pytest

from packaging._range_utils import (
    FULL_RANGE,
    NEG_INF,
    POS_INF,
    BoundaryKind,
    BoundaryVersion,
    LowerBound,
    UpperBound,
    _after_locals_successor,
    _lowest_release_at_or_above,
    canonical_lower,
    range_is_empty,
)
from packaging._version_utils import coerce_version, version_cmpkey
from packaging.ranges import VersionRange, _detect_equal_wildcard
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
    """``Specifier.to_range`` and ``SpecifierSet.to_range`` must produce
    the same range as the ``VersionRange.from_*`` factories."""

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
        # Complement preserves admit_arbitrary (False here), so the
        # non-version literal drops out: ``~(===wat)`` is "every version".
        assert "wat" not in comp
        assert "1.0" in comp
        assert comp._admit_arbitrary is False

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

    @pytest.mark.parametrize("spec", ["!=0.dev0", "!=0.*", "!=0.0.*"])
    def test_not_equal_at_minimum_is_canonical(self, spec: str) -> None:
        # The lower interval (-inf, 0.dev0) holds no version (nothing precedes
        # the PEP 440 minimum), so a single-specifier range must drop it to
        # match the SpecifierSet form (which folds through intersection). A
        # vestigial empty interval would break equality.
        r = VersionRange.from_specifier(Specifier(spec))
        assert r == SpecifierSet(spec).to_range()
        # ``to_specifier_set`` returns None: the only candidate encoding
        # is ``>=V.dev0`` (or its ``!=V.*``-paired form), whose recovered
        # set auto-detects prereleases=True while the source's ``!=`` -derived
        # range carries ``_prereleases=None``. The drift_guard reports this
        # mismatch as None rather than silently widening the filter set.
        assert r.to_specifier_set() is None


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

    def test_cache_survives_canonicalize(self) -> None:
        # Sort + dedup does not change the accepted version set, so the
        # cached range stays valid; the next ``to_range`` returns the same
        # instance instead of rebuilding.
        ss = SpecifierSet([Specifier(">=1.0"), Specifier("<2.0"), Specifier(">=1.0")])
        first = ss.to_range()
        str(ss)  # force canonicalization
        second = ss.to_range()
        assert second is first

    def test_cache_invalidates_on_prereleases_setter(self) -> None:
        # Setting prereleases flips the configured override, which is part
        # of structural equality (since membership reads it), so the
        # recomputed range is unequal to the first.
        ss = SpecifierSet(">=1.0")
        first = ss.to_range()
        ss.prereleases = True
        second = ss.to_range()
        assert second is not first
        assert second != first
        assert second._prereleases_configured is True
        assert first._prereleases_configured is None

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
        # SpecifierSet("") does not explicitly set prereleases=False, so the
        # PEP 440 default still admits a pre-release on its own.
        assert "1.0a1" in r

    @pytest.mark.parametrize(
        ("spec_str", "item"),
        [
            # Configured False excludes a parseable pre-release.
            ("", "1.0a1"),
            (">=1.0", "2.0a1"),
            (">=0.dev0", "1.0a1"),
            ("!=1.0", "2.0a1"),
            ("==1.0.*", "1.0a1"),
            ("<2.0", "1.0a1"),
            ("===1.0a1", "1.0a1"),
            # Configured False leaves non-pre-releases (and === non-version
            # literals) admitted, just like SpecifierSet.
            (">=1.0", "1.5"),
            ("===1.0", "1.0"),
            ("===wat", "wat"),
        ],
    )
    def test_membership_honors_explicit_prereleases_false(
        self, spec_str: str, item: str
    ) -> None:
        # ``in`` must mirror SpecifierSet.__contains__: an explicit
        # prereleases=False excludes parseable pre-releases from membership.
        ss = SpecifierSet(spec_str, prereleases=False)
        assert (item in ss.to_range()) == (item in ss)

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


class TestContainsMethod:
    """:meth:`VersionRange.contains` is the explicit-args form that
    ``__contains__`` forwards to."""

    def test_default_matches_in_operator_rangelike(self) -> None:
        r = SpecifierSet(">=1.0,<2.0").to_range()
        assert r.contains("1.5") == ("1.5" in r) is True
        assert r.contains("0.9") == ("0.9" in r) is False
        assert r.contains("2.0") == ("2.0" in r) is False

    def test_default_matches_in_operator_unparsable(self) -> None:
        r = SpecifierSet(">=1.0").to_range()
        assert r.contains("not-a-version") == ("not-a-version" in r) is False

    def test_prereleases_true_admits_prerelease_rejected_by_default(self) -> None:
        r = SpecifierSet(">=1.0", prereleases=False).to_range()
        assert "1.5a1" not in r
        assert r.contains("1.5a1", prereleases=True) is True

    def test_prereleases_false_rejects_prerelease_in_configured_true_range(
        self,
    ) -> None:
        r = SpecifierSet(">=1.0a1").to_range()
        assert "1.5a1" in r
        assert r.contains("1.5a1", prereleases=False) is False

    def test_prereleases_none_uses_range_configured_policy(self) -> None:
        # Mirrors the three tagged constructors in TestPrereleaseComposition:
        # autodetected True, autodetected None, and explicit False.
        r_auto_true = SpecifierSet(">=1.0a1").to_range()
        r_auto_none = SpecifierSet(">=1.0").to_range()
        r_explicit_false = SpecifierSet(">=1.0", prereleases=False).to_range()
        for r in (r_auto_true, r_auto_none, r_explicit_false):
            assert r.contains("1.5a1", prereleases=None) == ("1.5a1" in r)

    def test_installed_true_forces_prereleases_on_prerelease_version(self) -> None:
        r = SpecifierSet(">=1.0", prereleases=False).to_range()
        assert r.contains("1.5a1") is False
        assert r.contains("1.5a1", installed=True) is True

    def test_installed_true_noop_for_non_prerelease(self) -> None:
        r = SpecifierSet(">=1.0", prereleases=False).to_range()
        assert r.contains("1.5", installed=True) == r.contains("1.5") is True

    def test_installed_true_noop_for_unparsable_string(self) -> None:
        r = SpecifierSet(">=1.0").to_range()
        assert r.contains("not-a-version", installed=True) is False

    def test_installed_true_overrides_explicit_prereleases_false(self) -> None:
        # Per specifiers.py:1208-1209, installed=True unconditionally
        # reassigns prereleases=True when the guard fires, beating an
        # explicit False from the caller.
        r = SpecifierSet(">=1.0").to_range()
        ss = SpecifierSet(">=1.0")
        assert (
            r.contains("1.5a1", prereleases=False, installed=True)
            == ss.contains("1.5a1", prereleases=False, installed=True)
            is True
        )

    def test_full_range_admits_arbitrary_strings_regardless_of_overrides(
        self,
    ) -> None:
        r = VersionRange.full()
        assert r.contains("not-a-version") is True
        assert r.contains("not-a-version", prereleases=True) is True
        assert r.contains("not-a-version", prereleases=False) is True
        assert r.contains("not-a-version", installed=True) is True

    def test_eqeqeq_prerelease_literal_honors_prereleases_override(self) -> None:
        r = Specifier("===1.0a1").to_range()
        ss = SpecifierSet("===1.0a1")
        # Default autodetect admits the literal.
        assert r.contains("1.0a1") is True
        # Explicit False excludes a parseable pre-release literal, matching SS.
        assert (
            r.contains("1.0a1", prereleases=False)
            == ss.contains("1.0a1", prereleases=False)
            is False
        )
        # installed=True bumps prereleases back to True.
        assert r.contains("1.0a1", installed=True) is True

    def test_empty_range_contains_nothing_under_any_override(self) -> None:
        r = SpecifierSet(">=2.0,<1.0").to_range()
        for prereleases in (None, True, False):
            for installed in (None, True, False):
                for item in ("1.0", "1.5a1", "not-a-version"):
                    assert (
                        r.contains(item, prereleases=prereleases, installed=installed)
                        is False
                    )

    def test_reject_bearing_range_excludes_admit_literal(self) -> None:
        r = Specifier("===wat").to_range().complement()
        assert r.contains("wat") is False
        assert r.contains("wat", prereleases=True) is False
        assert r.contains("wat", installed=True) is False

    @pytest.mark.parametrize("spec_str", ["", ">=1.0", "===wat", "!=1.0"])
    @pytest.mark.parametrize("item", [None, 1, [], {}, 1.5])
    def test_off_type_item_raises_type_error_like_specifier_set(
        self,
        spec_str: str,
        item: object,
    ) -> None:
        # Non-str/non-Version inputs raise TypeError: both APIs reject silent
        # widening for items they cannot meaningfully test for membership.
        ss = SpecifierSet(spec_str)
        r = ss.to_range()
        with pytest.raises(TypeError, match="expected str or Version"):
            r.contains(item)  # type: ignore[arg-type]
        with pytest.raises(TypeError, match="expected str or Version"):
            ss.contains(item)  # type: ignore[arg-type]
        with pytest.raises(TypeError, match="expected str or Version"):
            item in r  # type: ignore[operator]  # noqa: B015
        with pytest.raises(TypeError, match="expected str or Version"):
            item in ss  # type: ignore[operator]  # noqa: B015

    @pytest.mark.parametrize(
        "spec_str",
        [
            ">=1.0",
            ">=1.0a1",
            "==1.0",
            "===1.0a1",
            ">=2.0,<1.0",
            "",
        ],
    )
    @pytest.mark.parametrize(
        "item",
        ["1.0", "1.5", "1.5a1", "not-a-version"],
    )
    @pytest.mark.parametrize("prereleases", [None, True, False])
    @pytest.mark.parametrize("installed", [None, True, False])
    def test_parity_oracle_against_specifier_set_contains(
        self,
        spec_str: str,
        item: str,
        prereleases: bool | None,
        installed: bool | None,
    ) -> None:
        ss = SpecifierSet(spec_str)
        r = ss.to_range()
        assert r.contains(
            item, prereleases=prereleases, installed=installed
        ) == ss.contains(item, prereleases=prereleases, installed=installed)


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

    @pytest.mark.parametrize(
        "spec",
        [
            ">=1.0.0,<1.0.post0,!=1.0",
            ">=1.0.post0,<1.0.post1,!=1.0.post0",
        ],
    )
    def test_vacuous_after_locals_interval_is_empty(self, spec: str) -> None:
        # !=V yields an exclusive AFTER_LOCALS(V) lower bound; its smallest
        # successor V.post0.dev0 is excluded by the <V.post0 upper, so no
        # version fits and every emptiness signal must agree.
        r = VersionRange.from_specifier_set(SpecifierSet(spec))
        assert r.is_empty
        assert not r
        assert r == VersionRange.empty()
        # Complement preserves admit_arbitrary (False here), so the result
        # has full bounds but does not equal ``full()`` (admit_arb=True).
        comp = r.complement()
        assert comp._bounds == VersionRange.full()._bounds
        assert comp._admit_arbitrary is False
        assert not r.is_prerelease_only


class TestEquality:
    def test_same_range_equal(self) -> None:
        r1 = VersionRange.from_specifier_set(SpecifierSet(">=1.0,<2.0"))
        r2 = VersionRange.from_specifier_set(SpecifierSet(">=1.0,<2.0"))
        assert r1 == r2

    def test_equivalent_specifiers_equal(self) -> None:
        # Two SpecifierSets that intersect to the same range yield equal
        # VersionRanges.
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

    def test_full_unequal_to_ge_dev0_specifier(self) -> None:
        # ``full()`` admits arbitrary strings; ``>=0.dev0`` reaches the same
        # bounds but does not. The slots that differ are part of equality
        # because membership reads them, so the two must compare unequal.
        full = VersionRange.full()
        ge = VersionRange.from_specifier(Specifier(">=0.dev0"))
        assert full != ge
        assert hash(full) != hash(ge)
        # Confirm membership disagrees, the reason eq must distinguish.
        assert "garbage" in full
        assert "garbage" not in ge

    def test_prereleases_configured_distinguishes_ranges(self) -> None:
        # Same bounds, opposite ``prereleases`` policy: explicit-False
        # rejects pre-releases under ``in`` while the autodetect-None
        # variant admits them, so eq and hash must distinguish.
        r_default = SpecifierSet(">=1.0").to_range()
        r_no_pre = SpecifierSet(">=1.0", prereleases=False).to_range()
        assert r_default != r_no_pre
        assert hash(r_default) != hash(r_no_pre)
        assert "1.5a1" in r_default
        assert "1.5a1" not in r_no_pre

    def test_equal_ranges_agree_under_every_observable(self) -> None:
        # eq/hash contract plus membership consistency: two ranges that
        # compare equal must agree on every observable membership check,
        # since eq compares the five slots membership reads. Pickle is
        # the cleanest twin source: it round-trips every slot eq inspects.
        cases = [
            SpecifierSet(">=1.0,<2.0").to_range(),
            SpecifierSet(">=1.0", prereleases=False).to_range(),
            SpecifierSet(">=1.0a1").to_range(),
            VersionRange.full(),
            VersionRange.empty(),
            VersionRange.singleton("1.5"),
            Specifier("===wat").to_range(),
            Specifier("===wat").to_range().complement(),
        ]
        items = ["1.0", "1.5", "1.5a1", "2.0", "wat", "garbage"]
        for r in cases:
            twin = pickle.loads(pickle.dumps(r))
            assert twin == r
            assert hash(twin) == hash(r)
            for item in items:
                assert (item in twin) == (item in r)
                assert twin.contains(item, prereleases=True) == r.contains(
                    item, prereleases=True
                )
                assert twin.contains(item, installed=True) == r.contains(
                    item, installed=True
                )


class TestRepr:
    @pytest.mark.parametrize(
        ("spec", "expected"),
        [
            (">=1.0,<2.0", "<VersionRange '[1.0, 2.0.dev0)'>"),
            (">=2.0,<1.0", "<VersionRange '(empty)'>"),
            ("", "<VersionRange '(-inf, +inf)' arbitrary>"),
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
        # AFTER_LOCALS / AFTER_POSTS bounds carry their kind into the repr.
        upper = VersionRange.from_specifier_set(SpecifierSet("<=1.0"))
        assert repr(upper) == "<VersionRange '(-inf, 1.0[AFTER_LOCALS]]'>"
        lower = VersionRange.from_specifier_set(SpecifierSet(">1.0"))
        assert repr(lower) == "<VersionRange '(1.0[AFTER_POSTS], +inf)'>"

    def test_repr_full_marks_arbitrary(self) -> None:
        assert repr(VersionRange.full()) == "<VersionRange '(-inf, +inf)' arbitrary>"

    def test_repr_empty_no_markers(self) -> None:
        assert repr(VersionRange.empty()) == "<VersionRange '(empty)'>"

    def test_repr_bounds_only_no_pre_config(self) -> None:
        r = VersionRange.from_specifier_set(SpecifierSet(">=1.0"))
        assert repr(r) == "<VersionRange '[1.0, +inf)'>"

    def test_repr_bounds_only_pre_false(self) -> None:
        r = VersionRange.from_specifier_set(SpecifierSet(">=1.0", prereleases=False))
        assert repr(r) == "<VersionRange '[1.0, +inf)' pre=False>"

    def test_repr_bounds_only_pre_true(self) -> None:
        r = VersionRange.from_specifier_set(SpecifierSet(">=1.0", prereleases=True))
        assert repr(r) == "<VersionRange '[1.0, +inf)' pre=True>"

    def test_repr_ge_zero_dev0_no_arbitrary(self) -> None:
        r = VersionRange.from_specifier(Specifier(">=0.dev0"))
        assert repr(r) == "<VersionRange '(-inf, +inf)'>"

    def test_repr_arbitrary_literal_no_marker(self) -> None:
        r = VersionRange.from_specifier(Specifier("===wat"))
        assert repr(r) == "<VersionRange '{wat}'>"

    def test_repr_disambiguates_full_vs_ge_zero_dev0(self) -> None:
        assert repr(VersionRange.full()) != repr(
            VersionRange.from_specifier(Specifier(">=0.dev0"))
        )

    def test_repr_disambiguates_pre_config(self) -> None:
        a = VersionRange.from_specifier_set(SpecifierSet(">=1.0"))
        b = VersionRange.from_specifier_set(SpecifierSet(">=1.0", prereleases=False))
        assert repr(a) != repr(b)

    def test_repr_disambiguates_singleton_vs_eq(self) -> None:
        # singleton('1.0') excludes 1.0+local; ==1.0 includes it. The
        # upper bounds differ structurally (bare Version vs AFTER_LOCALS
        # boundary) and the repr must surface that.
        s = VersionRange.singleton("1.0")
        eq = VersionRange.from_specifier(Specifier("==1.0"))
        assert repr(s) != repr(eq)
        assert s != eq

    def test_repr_disambiguates_ne_vs_complement_singleton(self) -> None:
        # !=1.0 admits 1.0+local; ~singleton('1.0') does not. The lower
        # bound of the upper interval differs (AFTER_LOCALS vs bare).
        ne = VersionRange.from_specifier(Specifier("!=1.0"))
        comp = ~VersionRange.singleton("1.0")
        assert repr(ne) != repr(comp)
        assert ne != comp


class _PickleSubclass(VersionRange):
    """Module-level subclass; pickle requires a non-local class to import."""


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

    def test_pickle_kind_is_stable_int_code(self) -> None:
        # The boundary-kind slot of the packed bound is an integer code
        # owned by ``ranges.py``, not the enum member's ``.name``. Renaming
        # the enum in ``_range_utils`` must not change these codes.
        # ``==1.0`` -> upper bound is ``AFTER_LOCALS(1.0)`` (code 1).
        # ``>1.0`` -> lower bound is ``AFTER_POSTS(1.0)`` (code 2).
        eq_state = VersionRange.from_specifier(Specifier("==1.0")).__getstate__()
        assert eq_state[0][0][1] == ("1.0", True, 1)
        gt_state = VersionRange.from_specifier(Specifier(">1.0")).__getstate__()
        assert gt_state[0][0][0] == ("1.0", False, 2)

    @staticmethod
    def _round_trip_cases() -> list[VersionRange]:
        # Every shape the public API can produce: bounded, unbounded,
        # arbitrary-admitting, ``===`` admit, set-algebra reject, all
        # three prerelease policies, and a union built from set ops.
        bounded = VersionRange.from_specifier_set(SpecifierSet(">=1.0,<2.0"))
        return [
            VersionRange.empty(),
            VersionRange.full(),
            VersionRange.singleton("1.0"),
            bounded,
            VersionRange.from_specifier_set(SpecifierSet("!=1.5")),
            VersionRange.from_specifier(Specifier("===wat")),
            VersionRange.from_specifier(Specifier("===wat")).complement(),
            Specifier(">=1.0a1").to_range(),
            SpecifierSet(">=1.0", prereleases=False).to_range(),
            SpecifierSet(">=1.0", prereleases=True).to_range(),
            bounded | VersionRange.singleton("3.0"),
        ]

    def test_pickle_preserves_subclass_type(self) -> None:
        original = _PickleSubclass.singleton("1.0")
        restored = pickle.loads(pickle.dumps(original))
        assert type(restored) is _PickleSubclass
        assert restored == original

    def test_copy_preserves_subclass_type(self) -> None:
        # ``copy.copy`` and ``copy.deepcopy`` go through ``__reduce__`` /
        # ``__setstate__`` the same way pickle does, so a local subclass
        # works here (copy does not need a re-importable qualname).
        class MyRange(VersionRange):
            pass

        original = MyRange.singleton("1.0")
        assert type(copy.copy(original)) is MyRange
        assert type(copy.deepcopy(original)) is MyRange

    def test_pickle_round_trip_preserves_eq_hash_repr(self) -> None:
        for r in self._round_trip_cases():
            restored = pickle.loads(pickle.dumps(r))
            assert restored == r
            assert hash(restored) == hash(r)
            assert repr(restored) == repr(r)

    def test_copy_round_trip_preserves_eq_hash_repr(self) -> None:
        for r in self._round_trip_cases():
            shallow = copy.copy(r)
            deep = copy.deepcopy(r)
            assert shallow == r == deep
            assert hash(shallow) == hash(r) == hash(deep)
            assert repr(shallow) == repr(r) == repr(deep)
            assert type(shallow) is type(r) is type(deep)

    @pytest.mark.parametrize(
        "bad_state",
        [
            None,
            "string",
            42,
            (),
            ((), (), (), True, None),  # 5-tuple, too short
            ((), (), (), True, None, None, "extra"),  # 7-tuple, too long
            ((), (), (), "not-a-bool", None, None),  # wrong admit_arbitrary type
            ((), [], (), True, None, None),  # admit isn't tuple
            ((), (), (), True, "not-bool-or-none", None),  # bad pre type
            (
                (((None, True, None),),),
                (),
                (),
                True,
                None,
                None,
            ),  # malformed bound pair
        ],
    )
    def test_setstate_rejects_malformed_state(self, bad_state: object) -> None:
        """``__setstate__`` mirrors sister classes: shape dispatch and a
        clear :exc:`TypeError` fallthrough so future-format pickles or junk
        input fail cleanly instead of leaking an :exc:`AttributeError` or
        :exc:`ValueError`."""
        r = VersionRange.empty()
        with pytest.raises(TypeError, match="Cannot restore VersionRange"):
            r.__setstate__(bad_state)

    # Pickle bytes generated with packaging 26.3 (initial VersionRange release),
    # CPython 3.13, pickle protocol 2. Pinning these catches accidental
    # format drift between releases without running the cross-release nox
    # session. Frozen ``BoundaryKind`` codes are 1 (AFTER_LOCALS) and 2
    # (AFTER_POSTS); never reuse a retired code.
    _PICKLE_FIXTURES: ClassVar[dict[str, tuple[bytes, VersionRange]]] = {
        "empty": (
            b"\x80\x02cpackaging.ranges\n_new_version_range\nq\x00cpackaging."
            b"ranges\nVersionRange\nq\x01\x85q\x02Rq\x03()))\x89NNtq\x04b.",
            VersionRange.empty(),
        ),
        "full": (
            b"\x80\x02cpackaging.ranges\n_new_version_range\nq\x00cpackaging."
            b"ranges\nVersionRange\nq\x01\x85q\x02Rq\x03(N\x89N\x87q\x04N"
            b"\x89N\x87q\x05\x86q\x06\x85q\x07))\x88NNtq\x08b.",
            VersionRange.full(),
        ),
        "singleton_1_0": (
            b"\x80\x02cpackaging.ranges\n_new_version_range\nq\x00cpackaging."
            b"ranges\nVersionRange\nq\x01\x85q\x02Rq\x03(X\x03\x00\x00\x00"
            b"1.0q\x04\x88N\x87q\x05X\x03\x00\x00\x001.0q\x06\x88N\x87q\x07"
            b"\x86q\x08\x85q\t))\x89NNtq\nb.",
            VersionRange.singleton("1.0"),
        ),
        "arbitrary_wat": (
            b"\x80\x02cpackaging.ranges\n_new_version_range\nq\x00cpackaging."
            b"ranges\nVersionRange\nq\x01\x85q\x02Rq\x03()X\x03\x00\x00\x00"
            b"watq\x04\x85q\x05)\x89NNtq\x06b.",
            Specifier("===wat").to_range(),
        ),
        "range_ge_1_lt_2_ne_1_5": (
            b"\x80\x02cpackaging.ranges\n_new_version_range\nq\x00cpackaging."
            b"ranges\nVersionRange\nq\x01\x85q\x02Rq\x03(X\x03\x00\x00\x00"
            b"1.0q\x04\x88N\x87q\x05X\x03\x00\x00\x001.5q\x06\x89N\x87q\x07"
            b"\x86q\x08X\x03\x00\x00\x001.5q\t\x89K\x01\x87q\nX\x08\x00\x00"
            b"\x002.0.dev0q\x0b\x89N\x87q\x0c\x86q\r\x86q\x0e))\x89NNtq\x0fb.",
            SpecifierSet(">=1.0,<2.0,!=1.5").to_range(),
        ),
        "after_locals_eq_1_0": (
            b"\x80\x02cpackaging.ranges\n_new_version_range\nq\x00cpackaging."
            b"ranges\nVersionRange\nq\x01\x85q\x02Rq\x03(X\x03\x00\x00\x00"
            b"1.0q\x04\x88N\x87q\x05X\x03\x00\x00\x001.0q\x06\x88K\x01\x87"
            b"q\x07\x86q\x08\x85q\t))\x89NNtq\nb.",
            SpecifierSet("==1.0").to_range(),
        ),
        "after_posts_gt_1_0": (
            b"\x80\x02cpackaging.ranges\n_new_version_range\nq\x00cpackaging."
            b"ranges\nVersionRange\nq\x01\x85q\x02Rq\x03(X\x03\x00\x00\x00"
            b"1.0q\x04\x89K\x02\x87q\x05N\x89N\x87q\x06\x86q\x07\x85q\x08"
            b"))\x89NNtq\tb.",
            SpecifierSet(">1.0").to_range(),
        ),
        "ge_1_pre_false": (
            b"\x80\x02cpackaging.ranges\n_new_version_range\nq\x00cpackaging."
            b"ranges\nVersionRange\nq\x01\x85q\x02Rq\x03(X\x03\x00\x00\x00"
            b"1.0q\x04\x88N\x87q\x05N\x89N\x87q\x06\x86q\x07\x85q\x08))"
            b"\x89\x89\x89tq\tb.",
            SpecifierSet(">=1.0", prereleases=False).to_range(),
        ),
        "ge_1a1_pre_true": (
            b"\x80\x02cpackaging.ranges\n_new_version_range\nq\x00cpackaging."
            b"ranges\nVersionRange\nq\x01\x85q\x02Rq\x03(X\x05\x00\x00\x00"
            b"1.0a1q\x04\x88N\x87q\x05N\x89N\x87q\x06\x86q\x07\x85q\x08))"
            b"\x89\x88Ntq\tb.",
            SpecifierSet(">=1.0a1").to_range(),
        ),
    }

    @pytest.mark.parametrize("fixture_name", sorted(_PICKLE_FIXTURES))
    def test_frozen_pickle_bytes_round_trip(self, fixture_name: str) -> None:
        """Frozen 26.3 pickle bytes load to the expected range. Format drift
        between releases breaks this; intentional changes regenerate the bytes
        here and bump the cross-release fixture in :mod:`tasks.pickle_compat`."""
        blob, expected = self._PICKLE_FIXTURES[fixture_name]
        restored = pickle.loads(blob)
        assert isinstance(restored, VersionRange)
        assert restored == expected
        assert hash(restored) == hash(expected)
        # PyPy's pickler emits BINGET in places where CPython emits
        # SHORT_BINUNICODE, so byte-equal re-pickle is CPython-only.
        if sys.implementation.name == "cpython":
            assert pickle.dumps(restored, protocol=2) == blob

    def test_setstate_rejects_unknown_boundary_kind_code(self) -> None:
        """An unknown ``BoundaryKind`` code surfaces as :exc:`TypeError`,
        not a bare :exc:`KeyError` from ``_CODE_TO_KIND``."""
        # Build a well-shaped 6-tuple with a single bound pair whose kind
        # code is not in ``_KIND_TO_CODE``.
        bad_state = (
            ((("1.0", True, 99), ("2.0", False, None)),),
            (),
            (),
            False,
            None,
            None,
        )
        r = VersionRange.empty()
        with pytest.raises(TypeError, match="Cannot restore VersionRange"):
            r.__setstate__(bad_state)


class TestBoundaryClosureEdgeCases:
    """Closure-based boundary checks on a parsed version whose release
    tuple is shorter than the bound version's trimmed release."""

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

    def test_after_posts_short_release_in_empty_check(self) -> None:
        # >1.0.0.0.5 leaves an AFTER_POSTS(1.0.0.0.5) lower bound; intersecting
        # with <2 compares it against 2.dev0, whose release is shorter than the
        # boundary's, exercising the short-release branch of the family check.
        r = VersionRange.from_specifier_set(SpecifierSet(">1.0.0.0.5,<2"))
        assert not r.is_empty
        assert "1.5" in r
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
            # All-zero / trailing-zero releases trim to () in Version._key.
            Version("0"),
            Version("0.0"),
            Version("0.0.0"),
            Version("1.0"),
            Version("1.0.0"),
            Version("2!0"),
            Version("0.0.dev0"),
            Version("0.0.post0"),
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


class TestBoundaryVersionInvariants:
    """Caller-side preconditions guarded by asserts in ``BoundaryVersion``.

    AFTER_POSTS folds V's post and dev into a synthetic suffix; AFTER_LOCALS
    relies on ``version_cmpkey``, which drops local. A version carrying any
    of those segments would collapse two distinct boundaries onto one
    ``_order_key`` while ``__eq__`` reported them unequal, breaking
    ``functools.total_ordering``.
    """

    @pytest.mark.parametrize(
        "version_str",
        ["1.0.post0", "1.0.dev0", "1.0+local", "1.0.post1.dev2"],
    )
    def test_after_posts_rejects_post_dev_or_local(self, version_str: str) -> None:
        with pytest.raises(AssertionError):
            BoundaryVersion(Version(version_str), BoundaryKind.AFTER_POSTS)

    def test_after_locals_rejects_local(self) -> None:
        with pytest.raises(AssertionError):
            BoundaryVersion(Version("1.0+abc"), BoundaryKind.AFTER_LOCALS)

    @pytest.mark.parametrize(
        "version_str",
        ["1.0", "1.0a1", "2!1.0rc1", "1.0.post0", "1.0.dev0", "1.0.post1.dev2"],
    )
    def test_after_locals_accepts_post_or_dev(self, version_str: str) -> None:
        # AFTER_LOCALS keeps V's full suffix in the order key, so post and
        # dev are fine; only local must be absent.
        BoundaryVersion(Version(version_str), BoundaryKind.AFTER_LOCALS)


class TestLowestReleaseAtOrAbove:
    """``_lowest_release_at_or_above`` feeds the prerelease-only check.

    A pre-release's nearest non-pre-release is the bare release, so every
    pre/post/dev/local segment must be stripped. ``V.postN < V`` in PEP 440,
    so a lingering post would overshoot the real lowest release.
    """

    def test_none_returns_zero(self) -> None:
        # A None (-inf) lower has 0 as its nearest non-pre-release above.
        assert _lowest_release_at_or_above(None) == Version("0")

    def test_prerelease_strips_to_bare_release(self) -> None:
        assert _lowest_release_at_or_above(Version("1.0a1")) == Version("1.0")

    def test_prerelease_with_post_strips_post(self) -> None:
        # 1.0a1.post3 < 1.0, so the nearest non-pre is 1.0, not 1.0.post3.
        assert _lowest_release_at_or_above(Version("1.0a1.post3")) == Version("1.0")

    def test_prerelease_with_epoch_and_post(self) -> None:
        assert _lowest_release_at_or_above(Version("2!1.0rc1.post1")) == Version(
            "2!1.0"
        )

    def test_dev_only_with_post_keeps_post(self) -> None:
        # 1.0 < 1.0.post0.dev0 < 1.0.post0, so the nearest non-pre is
        # 1.0.post0 (a dev-only release keeps its post segment).
        assert _lowest_release_at_or_above(Version("1.0.post0.dev0")) == Version(
            "1.0.post0"
        )

    def test_dev_only_strips_to_bare_release(self) -> None:
        assert _lowest_release_at_or_above(Version("1.0.dev0")) == Version("1.0")

    def test_final_release_unchanged(self) -> None:
        assert _lowest_release_at_or_above(Version("1.0")) == Version("1.0")

    def test_post_release_unchanged(self) -> None:
        assert _lowest_release_at_or_above(Version("1.0.post1")) == Version("1.0.post1")

    def test_boundary_prerelease_strips_to_bare_release(self) -> None:
        bv = BoundaryVersion(Version("1.0a1"), BoundaryKind.AFTER_LOCALS)
        assert _lowest_release_at_or_above(bv) == Version("1.0")

    def test_boundary_prerelease_with_post_strips_post(self) -> None:
        bv = BoundaryVersion(Version("1.0a1.post2"), BoundaryKind.AFTER_LOCALS)
        assert _lowest_release_at_or_above(bv) == Version("1.0")

    def test_boundary_final_returns_post0(self) -> None:
        bv = BoundaryVersion(Version("1.0"), BoundaryKind.AFTER_LOCALS)
        assert _lowest_release_at_or_above(bv) == Version("1.0.post0")

    def test_boundary_post_returns_next_post(self) -> None:
        bv = BoundaryVersion(Version("1.0.post0"), BoundaryKind.AFTER_LOCALS)
        assert _lowest_release_at_or_above(bv) == Version("1.0.post1")


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

    def test_complement_of_empty_covers_every_version(self) -> None:
        # Complement preserves admit_arbitrary, so the empty range maps
        # to full bounds with admit_arbitrary=False, which covers every
        # version but stays distinct from ``full()``.
        comp = VersionRange.empty().complement()
        assert comp._bounds == VersionRange.full()._bounds
        assert comp._admit_arbitrary is False
        assert "1.0" in comp
        assert "garbage" not in comp

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

    def test_complement_of_unbounded_keeps_arbitrary_flag(self) -> None:
        # ``~full()`` keeps ``_admit_arbitrary`` as metadata; bounds are
        # empty so the flag fires no admission. Distinct from ``empty()``
        # but membership-empty.
        comp = VersionRange.full().complement()
        assert comp._admit_arbitrary is True
        assert not comp._bounds
        assert comp.is_empty
        assert "garbage" not in comp
        assert "1.0" not in comp
        assert comp != VersionRange.empty()
        assert comp == VersionRange.empty(admit_arbitrary=True)
        # Widening through union to FULL_RANGE bounds reactivates the flag.
        assert "garbage" in (comp | VersionRange.full())

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


class TestIdentityFactoryPrereleases:
    """``empty``/``full``/``singleton`` accept ``prereleases=`` so they
    can be combined with ranges that carry an explicit policy.
    """

    @pytest.mark.parametrize("policy", [True, False])
    def test_empty_stamps_policy(self, policy: bool) -> None:
        r = VersionRange.empty(prereleases=policy)
        assert r._prereleases_configured is policy
        assert r._prereleases is policy

    @pytest.mark.parametrize("policy", [True, False])
    def test_full_stamps_policy(self, policy: bool) -> None:
        r = VersionRange.full(prereleases=policy)
        assert r._prereleases_configured is policy
        assert r._prereleases is policy

    @pytest.mark.parametrize("policy", [True, False])
    def test_singleton_stamps_policy(self, policy: bool) -> None:
        r = VersionRange.singleton("1.0", prereleases=policy)
        assert r._prereleases_configured is policy
        assert r._prereleases is policy

    def test_default_keeps_autodetect(self) -> None:
        for r in (
            VersionRange.empty(),
            VersionRange.full(),
            VersionRange.singleton("1.0"),
            VersionRange.empty(prereleases=None),
            VersionRange.full(prereleases=None),
            VersionRange.singleton("1.0", prereleases=None),
        ):
            assert r._prereleases_configured is None
            assert r._prereleases is None

    @pytest.mark.parametrize("policy", [True, False])
    def test_lattice_identities(self, policy: bool) -> None:
        r = SpecifierSet(">=1.0", prereleases=policy).to_range()
        assert r & VersionRange.full(prereleases=policy) == r
        assert r | VersionRange.empty(prereleases=policy) == r
        assert r & VersionRange.empty(prereleases=policy) == VersionRange.empty(
            prereleases=policy
        )
        assert r | VersionRange.full(prereleases=policy) == VersionRange.full(
            prereleases=policy
        )

    def test_mismatch_still_raises(self) -> None:
        r = SpecifierSet(">=1.0", prereleases=False).to_range()
        with pytest.raises(ValueError, match="pre-release policies"):
            VersionRange.full(prereleases=True) & r

    def test_explicit_false_against_autodetect_true_raises(self) -> None:
        # Autodetected ``True`` from a prerelease bound is not the same
        # as a configured ``True``; the configured tag is what gates.
        auto = SpecifierSet(">=1.0a1").to_range()
        with pytest.raises(ValueError, match="pre-release policies"):
            auto & VersionRange.full(prereleases=True)

    def test_explicit_true_against_autodetect_range_raises(self) -> None:
        auto = SpecifierSet(">=1.0").to_range()
        with pytest.raises(ValueError, match="pre-release policies"):
            auto & VersionRange.empty(prereleases=True)

    @pytest.mark.parametrize("policy", [True, False])
    def test_pickle_round_trip_preserves_policy(self, policy: bool) -> None:
        for original in (
            VersionRange.empty(prereleases=policy),
            VersionRange.full(prereleases=policy),
            VersionRange.singleton("1.0", prereleases=policy),
        ):
            restored = pickle.loads(pickle.dumps(original))
            assert restored == original
            assert restored._prereleases_configured is policy
            assert restored._prereleases is policy

    @pytest.mark.parametrize("policy", [True, False])
    def test_repr_carries_pre_tag(self, policy: bool) -> None:
        tag = f"pre={policy}"
        assert tag in repr(VersionRange.empty(prereleases=policy))
        assert tag in repr(VersionRange.full(prereleases=policy))
        assert tag in repr(VersionRange.singleton("1.0", prereleases=policy))


class TestAdmitArbitraryFactory:
    """``full`` and ``empty`` accept ``admit_arbitrary=``. Defaults pin
    the identity elements of the propagation rules: ``full()`` defaults
    to ``True`` (identity of AND, so ``r & full() == r``); ``empty()``
    defaults to ``False`` (identity of OR, so ``r | empty() == r``).
    """

    def test_default_full_admits_arbitrary(self) -> None:
        r = VersionRange.full()
        assert r._admit_arbitrary is True
        assert "garbage" in r

    def test_default_empty_rejects_arbitrary(self) -> None:
        r = VersionRange.empty()
        assert r._admit_arbitrary is False
        assert "garbage" not in r

    def test_full_no_arbitrary_admits_versions_only(self) -> None:
        r = VersionRange.full(admit_arbitrary=False)
        assert r._admit_arbitrary is False
        assert r._bounds == VersionRange.full()._bounds
        assert "1.0" in r
        assert "garbage" not in r
        assert not r.is_empty
        assert bool(r) is True

    def test_empty_with_flag_is_membership_empty(self) -> None:
        r = VersionRange.empty(admit_arbitrary=True)
        assert r._admit_arbitrary is True
        assert r._bounds == ()
        assert "1.0" not in r
        assert "garbage" not in r
        assert r.is_empty
        assert bool(r) is False

    def test_full_default_matches_explicit_true(self) -> None:
        assert VersionRange.full() == VersionRange.full(admit_arbitrary=True)
        assert hash(VersionRange.full()) == hash(
            VersionRange.full(admit_arbitrary=True)
        )

    def test_empty_default_matches_explicit_false(self) -> None:
        assert VersionRange.empty() == VersionRange.empty(admit_arbitrary=False)
        assert hash(VersionRange.empty()) == hash(
            VersionRange.empty(admit_arbitrary=False)
        )

    def test_admit_arbitrary_distinguishes_full_variants(self) -> None:
        assert VersionRange.full(admit_arbitrary=True) != VersionRange.full(
            admit_arbitrary=False
        )
        assert hash(VersionRange.full(admit_arbitrary=True)) != hash(
            VersionRange.full(admit_arbitrary=False)
        )

    def test_admit_arbitrary_distinguishes_empty_variants(self) -> None:
        assert VersionRange.empty(admit_arbitrary=True) != VersionRange.empty(
            admit_arbitrary=False
        )
        assert hash(VersionRange.empty(admit_arbitrary=True)) != hash(
            VersionRange.empty(admit_arbitrary=False)
        )

    def test_full_no_arbitrary_equals_ge_dev0_specifier(self) -> None:
        # ``>=0.dev0`` reaches FULL_RANGE bounds without arbitrary
        # admission, the same shape ``admit_arbitrary=False`` produces.
        ge = VersionRange.from_specifier(Specifier(">=0.dev0"))
        no_arb = VersionRange.full(admit_arbitrary=False)
        assert no_arb == ge
        assert hash(no_arb) == hash(ge)

    def test_empty_with_flag_equals_complement_of_default_full(self) -> None:
        assert VersionRange.empty(admit_arbitrary=True) == ~VersionRange.full()
        assert hash(VersionRange.empty(admit_arbitrary=True)) == hash(
            ~VersionRange.full()
        )

    @pytest.mark.parametrize("admit_arbitrary", [True, False])
    def test_complement_round_trip_holds_for_full(self, admit_arbitrary: bool) -> None:
        r = VersionRange.full(admit_arbitrary=admit_arbitrary)
        assert ~~r == r

    @pytest.mark.parametrize("admit_arbitrary", [True, False])
    def test_complement_round_trip_holds_for_empty(self, admit_arbitrary: bool) -> None:
        r = VersionRange.empty(admit_arbitrary=admit_arbitrary)
        assert ~~r == r

    @pytest.mark.parametrize("admit_arbitrary", [True, False])
    def test_complement_maps_full_to_empty_at_same_flag(
        self, admit_arbitrary: bool
    ) -> None:
        assert ~VersionRange.full(
            admit_arbitrary=admit_arbitrary
        ) == VersionRange.empty(admit_arbitrary=admit_arbitrary)
        assert ~VersionRange.empty(
            admit_arbitrary=admit_arbitrary
        ) == VersionRange.full(admit_arbitrary=admit_arbitrary)

    def test_intersection_and_admit_arbitrary(self) -> None:
        true_full = VersionRange.full(admit_arbitrary=True)
        false_full = VersionRange.full(admit_arbitrary=False)
        combined = true_full & false_full
        assert combined._admit_arbitrary is False
        assert combined == false_full

    def test_union_ors_admit_arbitrary(self) -> None:
        true_full = VersionRange.full(admit_arbitrary=True)
        false_full = VersionRange.full(admit_arbitrary=False)
        combined = true_full | false_full
        assert combined._admit_arbitrary is True

    def test_intersection_with_empty_flag(self) -> None:
        e_flag = VersionRange.empty(admit_arbitrary=True)
        assert e_flag & VersionRange.full(admit_arbitrary=True) == e_flag
        # Intersect with the no-arbitrary full strips the flag.
        assert e_flag & VersionRange.full(admit_arbitrary=False) == VersionRange.empty()

    def test_union_of_two_empty_flags_stays_empty(self) -> None:
        r1 = VersionRange.empty(admit_arbitrary=True)
        r2 = VersionRange.empty(admit_arbitrary=True)
        combined = r1 | r2
        assert combined == VersionRange.empty(admit_arbitrary=True)
        assert combined.is_empty
        assert "garbage" not in combined

    def test_empty_flag_reactivates_through_union_to_full_bounds(self) -> None:
        # Carrying the True flag through union to FULL_RANGE relights
        # arbitrary admission on the result.
        r = VersionRange.empty(admit_arbitrary=True) | VersionRange.full(
            admit_arbitrary=False
        )
        assert r._bounds == VersionRange.full()._bounds
        assert r._admit_arbitrary is True
        assert "garbage" in r

    def test_to_specifier_set_for_default_full(self) -> None:
        assert VersionRange.full().to_specifier_set() == SpecifierSet("")

    def test_to_specifier_set_for_default_empty(self) -> None:
        assert VersionRange.empty().to_specifier_set() == SpecifierSet("<0")

    def test_to_specifier_set_for_empty_with_flag_is_none(self) -> None:
        # Empty bounds plus the flag has no PEP 440 form, so the flag
        # cannot be preserved through round-trip.
        assert VersionRange.empty(admit_arbitrary=True).to_specifier_set() is None
        assert VersionRange.empty(admit_arbitrary=True).to_specifier_sets() is None

    def test_to_specifier_set_for_full_no_arbitrary_under_explicit_false(self) -> None:
        # Explicit prereleases=False clamps at filter time, so the
        # encoder emits ``>=0`` and the drift guard passes.
        r = VersionRange.full(admit_arbitrary=False, prereleases=False)
        assert r.to_specifier_set() == SpecifierSet(">=0", prereleases=False)

    def test_to_specifier_set_for_full_no_arbitrary_default_is_none(self) -> None:
        # The canonical encoding ``>=0.dev0`` recovers prereleases=True
        # from its ``.dev0`` literal, disagreeing with the source's
        # autodetect-None tag; the drift guard returns None rather than
        # silently widening filter behavior.
        assert VersionRange.full(admit_arbitrary=False).to_specifier_set() is None

    def test_repr_distinguishes_variants(self) -> None:
        assert "arbitrary" in repr(VersionRange.full(admit_arbitrary=True))
        assert "arbitrary" not in repr(VersionRange.full(admit_arbitrary=False))
        assert "arbitrary" in repr(VersionRange.empty(admit_arbitrary=True))
        assert "arbitrary" not in repr(VersionRange.empty(admit_arbitrary=False))

    @pytest.mark.parametrize("admit_arbitrary", [True, False])
    def test_pickle_round_trip_preserves_admit_arbitrary(
        self, admit_arbitrary: bool
    ) -> None:
        for original in (
            VersionRange.empty(admit_arbitrary=admit_arbitrary),
            VersionRange.full(admit_arbitrary=admit_arbitrary),
        ):
            restored = pickle.loads(pickle.dumps(original))
            assert restored == original
            assert restored._admit_arbitrary is admit_arbitrary

    def test_admit_arbitrary_and_prereleases_combine(self) -> None:
        r = VersionRange.full(admit_arbitrary=False, prereleases=True)
        assert r._admit_arbitrary is False
        assert r._prereleases_configured is True
        assert r._prereleases is True
        r = VersionRange.empty(admit_arbitrary=True, prereleases=False)
        assert r._admit_arbitrary is True
        assert r._prereleases_configured is False
        assert r._prereleases is False

    def test_prereleases_only_caller_keeps_default_admit_arbitrary(self) -> None:
        assert VersionRange.full(prereleases=True)._admit_arbitrary is True
        assert VersionRange.full(prereleases=False)._admit_arbitrary is True
        assert VersionRange.empty(prereleases=True)._admit_arbitrary is False
        assert VersionRange.empty(prereleases=False)._admit_arbitrary is False

    def test_subclass_full_returns_subclass(self) -> None:
        class Sub(VersionRange):
            pass

        r = Sub.full(admit_arbitrary=False)
        assert isinstance(r, Sub)
        assert r._admit_arbitrary is False

    def test_subclass_empty_returns_subclass(self) -> None:
        class Sub(VersionRange):
            pass

        r = Sub.empty(admit_arbitrary=True)
        assert isinstance(r, Sub)
        assert r._admit_arbitrary is True

    def test_filter_no_arbitrary_excludes_unparsable(self) -> None:
        r = VersionRange.full(admit_arbitrary=False)
        assert list(r.filter(["1.0", "garbage", "2.0"])) == ["1.0", "2.0"]

    def test_empty_with_flag_filter_admits_nothing(self) -> None:
        r = VersionRange.empty(admit_arbitrary=True)
        assert list(r.filter(["1.0", "garbage", "2.0"])) == []


class TestCoverageCorners:
    """Targeted tests for branches the main suite would otherwise miss."""

    def test_wildcard_singular_rejects_prefix_mismatch(self) -> None:
        lower = LowerBound(Version("1.5.dev0"), inclusive=True)
        upper = UpperBound(Version("2.0.dev0"), inclusive=False)
        assert _detect_equal_wildcard(lower, upper) is None

    def test_wildcard_singular_rejects_non_increment(self) -> None:
        # Padded prefix matches but the last segments differ by != +1.
        # Inverted bounds; the encoder never lands here naturally.
        lower = LowerBound(Version("1.0.3.dev0"), inclusive=True)
        upper = UpperBound(Version("1.dev0"), inclusive=False)
        assert _detect_equal_wildcard(lower, upper) is None

    def test_filter_with_reject_excludes_literal(self) -> None:
        r = VersionRange._build(
            FULL_RANGE, reject=frozenset({"wat"}), admit_arbitrary=True
        )
        assert list(r.filter(["wat", "1.0"])) == ["1.0"]

    def test_filter_yields_unparsable_after_final(self) -> None:
        r = SpecifierSet(">=1.0").to_range() | Specifier("===wat").to_range()
        assert list(r.filter(["1.0", "wat"])) == ["1.0", "wat"]

    def test_filter_prerelease_in_admission_path(self) -> None:
        # ``_build`` keeps ``_prereleases=None`` and an out-of-bounds
        # admit literal keeps the admission path live, so the filter
        # takes the PEP 440 default branch.
        r = VersionRange._build(
            bounds=((LowerBound(Version("1.0a1"), inclusive=True), POS_INF),),
            admit=frozenset({"wat"}),
        )
        # No final: pre-release buffered then released.
        assert list(r.filter(["1.5a1"])) == ["1.5a1"]
        # Final first: pre-release dropped.
        assert list(r.filter(["1.0", "1.5a1"])) == ["1.0"]

    def test_is_prerelease_only_false_when_reject(self) -> None:
        r = VersionRange._build(
            FULL_RANGE, reject=frozenset({"wat"}), admit_arbitrary=True
        )
        assert not r.is_prerelease_only

    def test_is_prerelease_only_false_for_full(self) -> None:
        assert not VersionRange.full().is_prerelease_only

    def test_is_prerelease_only_true_for_prerelease_bounds(self) -> None:
        r = SpecifierSet(">=1.0a1,<1.0rc1").to_range()
        assert r.is_prerelease_only is True

    def test_coerce_version_non_str_non_version_returns_none(self) -> None:
        assert coerce_version(42) is None  # type: ignore[arg-type]


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

    def test_empty_gap_after_locals_coalesces(self) -> None:
        # ==1.0.post0 ends at AFTER_LOCALS(1.0.post0) (inclusive); >1.0.post0
        # starts at AFTER_LOCALS(1.0.post0) (exclusive). Touching boundaries
        # collapse, so the union is the single interval >=1.0.post0 (and
        # stays involutive under complement).
        a = VersionRange.from_specifier(Specifier("==1.0.post0"))
        b = VersionRange.from_specifier(Specifier(">1.0.post0"))
        u = a.union(b)
        assert u == VersionRange.from_specifier(Specifier(">=1.0.post0"))
        assert len(u._bounds) == 1
        assert u.complement().complement() == u

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

    def test_gt_v_post_n_matches_complement_of_le(self) -> None:
        # ``>V.postN`` and ``~(<=V.postN)`` admit the same versions and
        # must share one canonical bound shape, or lattice distributivity
        # breaks for ranges that touch the V.postN[AFTER_LOCALS] boundary.
        ra = VersionRange.from_specifier_set(SpecifierSet(">=1.0.post0,!=1.0.post0"))
        rb = ~ra
        rc = VersionRange.from_specifier_set(SpecifierSet(">1.0.post0"))
        assert ra & (rb | rc) == (ra & rb) | (ra & rc)

    def test_gt_v_dev_n_matches_complement_of_le(self) -> None:
        # Same distributivity check for the dev-segment shape.
        ra = VersionRange.from_specifier_set(SpecifierSet(">=1.0.dev0,!=1.0.dev0"))
        rb = ~ra
        rc = VersionRange.from_specifier_set(SpecifierSet(">1.0.dev0"))
        assert ra & (rb | rc) == (ra & rb) | (ra & rc)


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

    def test_intersection_with_non_range_raises_typeerror(self) -> None:
        # The method paths must reject wrong-typed operands with the
        # same TypeError the ``&``/``|`` operators raise, rather than
        # leaking an AttributeError from internal slot access.
        a = VersionRange.from_specifier(Specifier(">=1.0"))
        with pytest.raises(TypeError):
            a.intersection("not a range")  # type: ignore[arg-type]
        with pytest.raises(TypeError):
            a.union(42)  # type: ignore[arg-type]

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

    def test_ge_dev0_range_encodes_as_ge_dev0_not_empty(self) -> None:
        # FULL_RANGE bounds without arbitrary-string admission must encode
        # to ``>=0.dev0``, not ``SpecifierSet("")``: the latter admits
        # arbitrary strings, which the source range does not.
        r = SpecifierSet(">=0.dev0").to_range()
        assert "wat" not in r
        rt = r.to_specifier_set()
        assert rt == SpecifierSet(">=0.dev0")
        assert "wat" not in rt
        assert rt != SpecifierSet("")
        assert VersionRange.from_specifier_set(rt) == r

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

    @pytest.mark.parametrize(
        "spec",
        [
            ">1.0.post0",
            ">1.0.dev0",
            ">1.0a1.post0",
            ">1.0a1.dev0",
            ">1.0.post0.dev0",
            ">1.0a1.post0.dev0",
            ">1!1.0.post0",
            ">1!1.0.dev0",
        ],
    )
    def test_gt_v_post_or_dev_round_trips_via_gt(self, spec: str) -> None:
        # ``>V`` where V has a post or dev segment round-trips as ``>V``:
        # PEP 440's exclusive-comparison post-release rule does not fire
        # when V already carries post/dev, so a single ``>V`` fragment
        # captures the semantics without any synthetic dev0 artifact.
        assert str(SpecifierSet(spec).to_range().to_specifier_set()) == spec

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

    def test_dev0_release_lengths_differ_chain_returns_none(self) -> None:
        # The gap [1.dev0, 1.2.dev0) decomposes into ``!=1.0.*,!=1.1.*``,
        # which auto-detects prereleases=None while the source carries
        # ``_prereleases=True`` from the ``.dev0`` operands. Both entry
        # points report ``None``.
        a = VersionRange.from_specifier(Specifier("<1.dev0"))
        b = VersionRange.from_specifier_set(SpecifierSet(">=1.2.dev0"))
        u = a | b
        assert u.to_specifier_set() is None
        assert u.to_specifier_sets() is None

    def test_unaligned_dev0_increment_returns_none(self) -> None:
        # ``==1.* | ==3.*`` has no single-SpecifierSet form: the merged
        # ``>=1.dev0,<4,!=2.*`` would flip prereleases auto-detect from
        # ``None`` to ``True``. ``to_specifier_sets`` returns the clean
        # per-wildcard split instead.
        a = VersionRange.from_specifier(Specifier("==1.*"))
        b = VersionRange.from_specifier(Specifier("==3.*"))
        u = a | b
        assert u.to_specifier_set() is None
        assert u.to_specifier_sets() == (
            SpecifierSet("==1.*"),
            SpecifierSet("==3.*"),
        )

    def test_dev0_anchored_union_returns_none_on_collapse_drift(self) -> None:
        # ``<1.0.dev0 | >=2.0.dev0`` leaves the gap [1.dev0, 2.dev0) = ==1.*.
        # The candidate ``!=1.*`` auto-detects prereleases=None while the
        # source carries ``_prereleases=True`` from the ``.dev0`` operands,
        # so both entry points refuse the encoding.
        a = VersionRange.from_specifier(Specifier("<1.0.dev0"))
        b = VersionRange.from_specifier_set(SpecifierSet(">=2.0.dev0"))
        u = a | b
        assert u.to_specifier_set() is None
        assert u.to_specifier_sets() is None

    def test_v_exclusive_lower_bound_is_not_encodable(self) -> None:
        # ``~singleton(V)`` produces two ``V (excl)`` bounds. The
        # second interval's V-exclusive lower has no specifier form.
        s = VersionRange.singleton("1.5")
        c = s.complement()
        assert c.to_specifier_set() is None
        assert c.to_specifier_sets() is None

    def test_to_specifier_sets_returns_none_when_full_range_would_drift(
        self,
    ) -> None:
        # ``>=0 | <=0`` reaches FULL_RANGE bounds with autodetect
        # ``_prereleases=None``. The encoder would emit ``>=0.dev0``,
        # whose own autodetect resolves to ``True``, so the drift guard
        # returns ``None``.
        ra = VersionRange.from_specifier_set(SpecifierSet(">=0"))
        rb = VersionRange.from_specifier_set(SpecifierSet("<=0"))
        uni = ra | rb
        assert uni._prereleases is None
        assert uni.to_specifier_sets() is None

    def test_to_specifier_sets_returns_none_when_pieces_lose_prerelease_signal(
        self,
    ) -> None:
        # ``>=0,>=0a0`` autodetects ``_prereleases=True`` from ``0a0``,
        # but the bounds canonicalize to ``[0, +inf)`` so the encoder
        # would emit ``(>=0,)``, whose autodetect resolves to ``None``.
        r = VersionRange.from_specifier_set(SpecifierSet(">=0,>=0a0"))
        assert r._prereleases is True
        assert r.to_specifier_sets() is None

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

    def test_wide_wildcard_gap_returns_none(self) -> None:
        # A multi-family wildcard span shares the artifact above: ``==1.*
        # | ==5.*`` cannot be a single SpecifierSet without the dev0
        # drift. ``to_specifier_sets`` keeps each kept family separate.
        a = VersionRange.from_specifier(Specifier("==1.*"))
        b = VersionRange.from_specifier(Specifier("==5.*"))
        u = a | b
        assert u.to_specifier_set() is None
        assert u.to_specifier_sets() == (
            SpecifierSet("==1.*"),
            SpecifierSet("==5.*"),
        )

    @pytest.mark.parametrize(
        ("spec_str", "expected"),
        [
            # Adjacent wildcards: gap covers two consecutive families.
            ("!=1.9.*,!=1.10.*", "!=1.9.*,!=1.10.*"),
            # Subsuming: 2.0.* lies inside 2.*; the canonical form is !=2.*.
            ("!=2.0.*,!=2.*", "!=2.*"),
        ],
    )
    def test_to_specifier_set_decomposes_wildcard_chain(
        self, spec_str: str, expected: str
    ) -> None:
        # Adjacent or subsuming != wildcards merge into one wide gap, but the
        # gap is still expressible as a chain of !=V.* exclusions.
        r = VersionRange.from_specifier_set(SpecifierSet(spec_str))
        encoded = r.to_specifier_set()
        assert encoded is not None
        assert encoded == SpecifierSet(expected)
        assert encoded.to_range() == r

    def test_to_specifier_set_decomposes_mixed_length_wildcard_chain(self) -> None:
        # The gap [1.0.dev0, 1.0.5.dev0) needs length-3 prefixes from a length-2
        # left bound; the decomposition extends the prefix and recurses.
        members = [Specifier(f"!=1.0.{n}.*") for n in range(5)]
        ss = SpecifierSet(members)
        r = ss.to_range()
        encoded = r.to_specifier_set()
        assert encoded is not None
        assert encoded.to_range() == r
        # Every chain fragment must be present (set may sort differently).
        assert {str(s) for s in encoded} == {str(s) for s in ss}

    def test_to_specifier_set_returns_none_for_undecomposable_gap(self) -> None:
        # The gap [1.0.0.5.dev0, 1.0.1.dev0) cannot be covered by any finite
        # chain of ==P.* families: L sits inside the (1.0.0)-subtree and the
        # chain can only increment within that subtree, never escaping to
        # reach 1.0.1. The disjoint union has no single SpecifierSet form,
        # but to_specifier_sets still returns the two-group split.
        a = VersionRange.from_specifier(Specifier("<1.0.0.5.dev0"))
        b = VersionRange.from_specifier_set(SpecifierSet(">=1.0.1.dev0"))
        u = a | b
        assert u.to_specifier_set() is None
        sets = u.to_specifier_sets()
        assert sets is not None
        assert len(sets) == 2

    @pytest.mark.parametrize("spec_str", ["==1.*", "==2.0.*", "==1.0.0.*", "==1!2.*"])
    def test_equal_wildcard_round_trips_without_dev0_artifact(
        self, spec_str: str
    ) -> None:
        # ``==V.*`` would round-trip through ``>=V.dev0,<NextV``, whose
        # synthetic ``.dev0`` flips :attr:`SpecifierSet.prereleases`
        # auto-detect from ``None`` to ``True``. The encoder emits the
        # wildcard form directly so the policy survives.
        ss = SpecifierSet(spec_str)
        rt = ss.to_range().to_specifier_set()
        assert rt == SpecifierSet(spec_str)
        assert rt.prereleases is None

    @pytest.mark.parametrize(
        ("spec_str", "configured"),
        [
            ("==1.*", True),
            ("==1.*", False),
            (">=1.0,<2.0", True),
            (">=1.0,<2.0", False),
            ("===abc", True),
            ("===abc", False),
        ],
    )
    def test_round_trip_preserves_configured_prereleases(
        self, spec_str: str, configured: bool
    ) -> None:
        ss = SpecifierSet(spec_str, prereleases=configured)
        rt = ss.to_range().to_specifier_set()
        assert rt is not None
        assert rt._prereleases is configured

    def test_round_trip_preserves_autodetect_none(self) -> None:
        # cfg=None must round-trip as cfg=None even when the encoded
        # specs would auto-detect True (synthetic ``.dev0`` literals).
        ss = SpecifierSet("==1.*")
        rt = ss.to_range().to_specifier_set()
        assert rt is not None
        assert rt._prereleases is None
        assert rt.prereleases is None
        assert list(ss.filter(["1.0a1", "1.0"])) == list(rt.filter(["1.0a1", "1.0"]))

    @pytest.mark.parametrize(
        ("left", "right"),
        [
            ("==1.*", "==3.*"),
            ("==1.*", "==5.*"),
            ("==1.0.*", "==1.2.*"),
            ("==1.0.*", "==1.1.*"),
        ],
    )
    def test_multi_wildcard_union_returns_none(self, left: str, right: str) -> None:
        # Any disjoint union of two ``==V.*`` families has no single-set
        # form: the merged outer ``[V.dev0, W.dev0)`` would carry a
        # ``>=V.dev0`` artifact that flips prereleases auto-detect.
        u = SpecifierSet(left).to_range() | SpecifierSet(right).to_range()
        assert u.to_specifier_set() is None

    def test_collapsing_adjacent_wildcards_returns_none(self) -> None:
        # ``==1.* | ==2.*`` canonicalises to ``[1.dev0, 3.dev0)`` (a
        # single interval) but still encodes via two ``==V.*`` groups, so
        # there is no single-set form.
        u = SpecifierSet("==1.*").to_range() | SpecifierSet("==2.*").to_range()
        assert u.to_specifier_set() is None

    def test_cross_epoch_interval_skips_wildcard_split(self) -> None:
        # ``[1.dev0, 1!1.dev0)`` straddles epochs, so the wildcard
        # decomposition bails at the epoch check and the standard
        # ``>=1.dev0,<1!1`` encoding takes over.
        r = SpecifierSet(">=1.dev0,<1!1.dev0").to_range()
        assert r.to_specifier_set() == SpecifierSet(">=1.dev0,<1!1")

    @pytest.mark.parametrize("v", ["1.0", "1!1.0"])
    def test_complement_of_lt_v_returns_none_under_autodetect(self, v: str) -> None:
        # Complement of ``<V`` produces ``>=V.dev0`` whose recovered
        # prereleases auto-detects True while the source has cfg=None
        # and _prereleases=None: the drift_guard reports None.
        assert SpecifierSet(f"<{v}").to_range().complement().to_specifier_set() is None

    def test_lt_v_post_n_returns_none_under_autodetect(self) -> None:
        # ``<V.postN`` produces the ``<=V.postN.dev0,!=V.postN.dev0`` pair;
        # both ``<=`` and ``!=`` fragments leak the synthetic dev0 marker.
        assert SpecifierSet("<1.0.post1").to_range().to_specifier_set() is None
        assert (
            SpecifierSet("<1.0.post1").to_range().complement().to_specifier_set()
            is None
        )

    def test_gt_v_post_n_complement_round_trips_via_le(self) -> None:
        # ``~(>V.postN)`` shares its bound shape with ``<=V.postN``, so
        # the complement round-trips to a single ``<=V.postN`` set.
        rt = SpecifierSet(">1.0.post0").to_range().complement().to_specifier_set()
        assert rt == SpecifierSet("<=1.0.post0")

    def test_lt_zero_complement_returns_none_under_autodetect(self) -> None:
        # ``<0`` is empty; complement is FULL_RANGE non-arbitrary, which
        # encodes as ``>=0.dev0`` (auto-detect True). Drift from cfg=None.
        assert SpecifierSet("<0").to_range().complement().to_specifier_set() is None

    def test_full_range_from_algebra_returns_none_under_autodetect(self) -> None:
        # ``r | ~r`` produces a FULL_RANGE non-arbitrary range with
        # _prereleases derived from algebra; cfg stays None, so the
        # ``>=0.dev0`` recovery drifts auto-detect.
        r = VersionRange.from_specifier_set(SpecifierSet("<2.0"))
        assert (r | r.complement()).to_specifier_set() is None

    @pytest.mark.parametrize("v", ["1.0.dev0", "1!1.0.dev0"])
    def test_lt_v_dev0_drift_returns_none_under_autodetect(self, v: str) -> None:
        # Source ``<V.dev0`` has _prereleases=True (autodetect via the
        # .dev0 literal). Encoder strips the synthetic dev0 to ``<V``,
        # whose recovered auto-detect falls back to None: opposite-
        # direction drift, caught by the same guard.
        assert SpecifierSet(f"<{v}").to_range().to_specifier_set() is None

    @pytest.mark.parametrize("v", ["1.0.dev0", "1!1.0.dev0"])
    def test_not_equal_v_dev0_complement_returns_none_under_autodetect(
        self, v: str
    ) -> None:
        # ``==V.dev0`` has _prereleases=True; complement emits ``!=V.dev0``
        # whose ``!=`` operator does not trigger SpecifierSet's prereleases
        # auto-detect, so recovered.prereleases is None. Drift.
        assert (~SpecifierSet(f"=={v}").to_range()).to_specifier_set() is None

    def test_complement_compatible_release_dev0_returns_none_under_autodetect(
        self,
    ) -> None:
        # ``~=1.0.dev0`` source has _prereleases=True; complement collapses
        # to ``!=1.*`` which auto-detects to None. Drift.
        assert (~SpecifierSet("~=1.0.dev0").to_range()).to_specifier_set() is None

    def test_complement_admit_only_returns_none_under_autodetect(self) -> None:
        # ``===wat`` admits only the literal "wat"; complement is FULL_RANGE
        # non-arbitrary, encoding as ``>=0.dev0`` (auto-detect True) while
        # the source had _prereleases=None.
        assert (~SpecifierSet("===wat").to_range()).to_specifier_set() is None

    @pytest.mark.parametrize("v", ["1.0", "1!1.0"])
    def test_complement_of_lt_v_cleans_to_ge_v_under_cfg_false(self, v: str) -> None:
        # Explicit prereleases=False clamps pre-releases at filter time
        # regardless of bound shape; cleanup_rewrite emits ``>=V`` instead
        # of ``>=V.dev0``.
        ss = SpecifierSet(f"<{v}", prereleases=False)
        rt = ss.to_range().complement().to_specifier_set()
        assert rt == SpecifierSet(f">={v}", prereleases=False)
        assert rt._prereleases is False
        # FILTER-equivalent (not structurally equal): rewrite holds under
        # the explicit clamp.
        src = ss.to_range().complement()
        probes = ["0.5a1", "1.0", "1.0a1", "1.0.dev0", "1.5", "2.0"]
        assert list(src.filter(probes)) == list(rt.filter(probes))

    def test_lt_v_post_n_cleans_to_le_v_post_n_pair_under_cfg_false(self) -> None:
        rt = SpecifierSet("<1.0.post1", prereleases=False).to_range().to_specifier_set()
        assert rt == SpecifierSet("<=1.0.post1,!=1.0.post1", prereleases=False)
        assert rt._prereleases is False

    def test_complement_of_lt_v_post_n_cleans_to_ge_v_post_n_under_cfg_false(
        self,
    ) -> None:
        rt = (
            SpecifierSet("<1.0.post1", prereleases=False)
            .to_range()
            .complement()
            .to_specifier_set()
        )
        assert rt == SpecifierSet(">=1.0.post1", prereleases=False)
        assert rt._prereleases is False

    def test_gt_v_post_n_round_trips_under_cfg_false(self) -> None:
        # The encoder emits ``>V.postN`` directly (no synthetic dev0 to
        # strip), so the cfg=False cleanup pass leaves it alone.
        rt = SpecifierSet(">1.0.post0", prereleases=False).to_range().to_specifier_set()
        assert rt == SpecifierSet(">1.0.post0", prereleases=False)
        assert rt._prereleases is False

    def test_lt_zero_complement_cleans_to_ge_zero_under_cfg_false(self) -> None:
        # FULL_RANGE non-arbitrary under cfg=False emits ``>=0`` instead
        # of ``>=0.dev0``; the cleaner spelling preserves the
        # non-arbitrary nature (``SpecifierSet("")`` would re-introduce
        # arbitrary-string admission).
        empty = SpecifierSet("<0", prereleases=False).to_range()
        rt = empty.complement().to_specifier_set()
        assert rt == SpecifierSet(">=0", prereleases=False)
        assert rt._prereleases is False
        assert "wat" not in VersionRange.from_specifier_set(rt)

    @pytest.mark.parametrize("v", ["1.0", "0", "1!1.0"])
    def test_ge_v_dev0_explicit_stays_faithful_under_autodetect(self, v: str) -> None:
        # Source explicitly writes ``.dev0``; _prereleases=True from
        # auto-detect. Recovered ``>=V.dev0`` also auto-detects True, no
        # drift, no cleanup.
        rt = SpecifierSet(f">={v}.dev0").to_range().to_specifier_set()
        assert rt == SpecifierSet(f">={v}.dev0")
        assert rt.prereleases is True

    def test_ge_zero_dev0_full_range_stays_faithful_under_autodetect(self) -> None:
        # FULL_RANGE non-arbitrary from explicit ``>=0.dev0`` keeps the
        # faithful encoding under cfg=None.
        r = SpecifierSet(">=0.dev0").to_range()
        rt = r.to_specifier_set()
        assert rt == SpecifierSet(">=0.dev0")
        assert "wat" not in rt
        assert "wat" not in r

    @pytest.mark.parametrize("spec", ["==1.*", "==2.0.*", "==1.0.0.*", "==1!2.*"])
    def test_equal_wildcard_round_trips_without_dev0_drift(self, spec: str) -> None:
        rt = SpecifierSet(spec).to_range().to_specifier_set()
        assert rt == SpecifierSet(spec)
        assert rt.prereleases is None

    @pytest.mark.parametrize(
        "spec",
        [
            ">=1.0",
            "<=1.0",
            ">1.0",
            "==1.5+local",
            "!=1.0+foo",
            "<2.0,>=1.0",
            "~=1.0",
            "==1.*",
        ],
    )
    @pytest.mark.parametrize("cfg", [None, True, False])
    def test_simple_ranges_stay_faithful_under_all_cfg_states(
        self, spec: str, cfg: bool | None
    ) -> None:
        ss = SpecifierSet(spec, prereleases=cfg)
        rt = ss.to_range().to_specifier_set()
        assert rt is not None
        assert rt._prereleases == cfg

    @pytest.mark.parametrize("cfg", [None, True, False])
    def test_complement_of_le_stays_faithful_via_ne_ge_pair(
        self, cfg: bool | None
    ) -> None:
        # AFTER_LOCALS lower encodes as ``>=V,!=V`` with no synthetic dev0;
        # faithful across all cfg states.
        le1 = SpecifierSet("<=1.0", prereleases=cfg).to_range()
        rt = le1.complement().to_specifier_set()
        assert rt == SpecifierSet(">=1.0,!=1.0", prereleases=cfg)

    @pytest.mark.parametrize("cfg", [None, True, False])
    def test_after_posts_inclusive_upper_stays_none(self, cfg: bool | None) -> None:
        # Complement of ``>V`` yields an inclusive AFTER_POSTS upper with
        # no specifier form, regardless of cfg.
        gt1 = SpecifierSet(">1.0", prereleases=cfg).to_range()
        assert gt1.complement().to_specifier_set() is None

    @pytest.mark.parametrize("cfg", [None, True, False])
    def test_full_range_with_admit_arbitrary_stays_empty_specifier_set(
        self, cfg: bool | None
    ) -> None:
        r = VersionRange.full()
        if cfg is not None:
            # The constructor freezes ``_prereleases_configured``; this test
            # exercises the encoder's reading of the slot regardless of how
            # it got set.
            r._prereleases_configured = cfg
            r._prereleases = cfg
        rt = r.to_specifier_set()
        assert rt is not None
        assert str(rt) == ""

    def test_dev0_anchored_union_returns_none_via_specifier_sets(self) -> None:
        # ``!=1.*`` would auto-detect prereleases=None while the source
        # carries ``_prereleases=True``, so the drift guard rejects it.
        a = VersionRange.from_specifier(Specifier("<1.0.dev0"))
        b = VersionRange.from_specifier_set(SpecifierSet(">=2.0.dev0"))
        assert (a | b).to_specifier_sets() is None

    def test_wildcard_detection_normalizes_short_lower_release(self) -> None:
        # Intersecting ``==1.*`` with ``==1.0.*`` yields a range structurally
        # equal to ``==1.0.*``; the lower bound's release tuple is ``(1,)``
        # while ``==1.0.*`` has ``(1, 0)``. Both ranges share __eq__ and hash,
        # so the wildcard encoder must normalize trailing zeros before
        # comparing prefix and last+1.
        a = VersionRange.from_specifier(
            Specifier("==1.*")
        ) & VersionRange.from_specifier(Specifier("==1.0.*"))
        b = VersionRange.from_specifier(Specifier("==1.0.*"))
        assert a == b
        assert hash(a) == hash(b)
        assert a.to_specifier_set() == SpecifierSet("==1.0.*")
        assert b.to_specifier_set() == SpecifierSet("==1.0.*")

    def test_wildcard_detection_normalizes_short_upper_release(self) -> None:
        # Symmetric to the short-lower case: ``(==1.0.0.*) & (==1.0.*)`` has
        # a lower release of ``(1, 0, 0)`` and an upper release of ``(1, 1)``;
        # after trim/pad both reduce to a clean ``==1.0.0.*`` wildcard.
        a = VersionRange.from_specifier(
            Specifier("==1.0.0.*")
        ) & VersionRange.from_specifier(Specifier("==1.0.*"))
        b = VersionRange.from_specifier(Specifier("==1.0.0.*"))
        assert a == b
        assert a.to_specifier_set() == SpecifierSet("==1.0.0.*")

    def test_wildcard_detection_normalizes_short_lower_with_epoch(self) -> None:
        a = VersionRange.from_specifier(
            Specifier("==1!1.*")
        ) & VersionRange.from_specifier(Specifier("==1!1.0.*"))
        b = VersionRange.from_specifier(Specifier("==1!1.0.*"))
        assert a == b
        assert a.to_specifier_set() == SpecifierSet("==1!1.0.*")

    def test_wildcard_detection_normalizes_short_lower_deep_release(self) -> None:
        # Lower release ``(1,)``, upper release ``(1, 0, 1)``: trim to
        # ``(1,)`` and ``(1, 0, 1)``, pad lower to ``(1, 0, 0)``. Output
        # ``==1.0.0.*``.
        a = VersionRange.from_specifier(
            Specifier("==1.*")
        ) & VersionRange.from_specifier(Specifier("==1.0.0.*"))
        b = VersionRange.from_specifier(Specifier("==1.0.0.*"))
        assert a == b
        assert a.to_specifier_set() == SpecifierSet("==1.0.0.*")

    @pytest.mark.parametrize(
        ("wider", "narrower"),
        [
            ("==1.*", "==1.0.*"),
            ("==1.*", "==1.0.0.*"),
            ("==2.*", "==2.5.*"),
            ("==1!1.*", "==1!1.0.*"),
            ("==1.0.*", "==1.0.0.*"),
            ("==1.99.*", "==1.99.0.*"),
        ],
    )
    def test_wildcard_detection_equal_hash_yields_equal_specifier_set(
        self, wider: str, narrower: str
    ) -> None:
        # Two ranges constructed via different code paths that hash and
        # compare equal must produce the same ``to_specifier_set`` output.
        a = VersionRange.from_specifier(Specifier(wider)) & VersionRange.from_specifier(
            Specifier(narrower)
        )
        b = VersionRange.from_specifier(Specifier(narrower))
        assert a == b
        assert hash(a) == hash(b)
        assert a.to_specifier_set() == b.to_specifier_set()


class TestToSpecifierSets:
    """``to_specifier_sets`` returns a tuple of SpecifierSets, or ``None``."""

    def test_full_range_returns_one_tuple_of_empty_specifier_set(self) -> None:
        assert VersionRange.full().to_specifier_sets() == (SpecifierSet(""),)

    def test_ge_dev0_range_returns_ge_dev0_tuple(self) -> None:
        # Same guard as ``to_specifier_set``: FULL_RANGE bounds with
        # ``_admit_arbitrary=False`` must not silently widen to
        # ``SpecifierSet("")``.
        r = SpecifierSet(">=0.dev0").to_range()
        assert r.to_specifier_sets() == (SpecifierSet(">=0.dev0"),)

    def test_empty_range_returns_lt_zero_tuple(self) -> None:
        assert VersionRange.empty().to_specifier_sets() == (SpecifierSet("<0"),)

    def test_singleton_returns_none(self) -> None:
        # Per-interval encoding of [V, V] also fails: the inclusive
        # upper bound has no specifier.
        assert VersionRange.singleton("1.5").to_specifier_sets() is None

    def test_autodetect_true_returns_none_when_bounds_drop_marker(self) -> None:
        # ``>=1.0a1 & >=2.0`` canonicalizes to ``>=2.0``, which
        # auto-detects prereleases=None and drops the source's
        # ``_prereleases=True`` signal. Both entry points refuse.
        r = VersionRange.from_specifier_set(
            SpecifierSet(">=1.0a1")
        ) & VersionRange.from_specifier_set(SpecifierSet(">=2.0"))
        assert r._prereleases_configured is None
        assert r._prereleases is True
        assert r.to_specifier_set() is None
        assert r.to_specifier_sets() is None

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

    @pytest.mark.parametrize("configured", [True, False])
    def test_round_trip_preserves_configured_prereleases(
        self, configured: bool
    ) -> None:
        ss = SpecifierSet(">=1.0,<2.0", prereleases=configured)
        sets = ss.to_range().to_specifier_sets()
        assert sets is not None
        for s in sets:
            assert s._prereleases is configured

    @pytest.mark.parametrize(
        ("left", "right", "expected"),
        [
            ("==1.*", "==3.*", ["==1.*", "==3.*"]),
            ("==1.*", "==5.*", ["==1.*", "==5.*"]),
            ("==1.0.*", "==1.2.*", ["==1.0.*", "==1.2.*"]),
            ("==1.*", ">=5.0", ["==1.*", ">=5.0"]),
        ],
    )
    def test_multi_wildcard_union_splits_into_per_family_sets(
        self, left: str, right: str, expected: list[str]
    ) -> None:
        # Adjacent ``==V.*`` wildcards joined by a ``!=X.*`` gap stay split
        # so each family encodes cleanly without the ``>=V.dev0`` artifact.
        u = SpecifierSet(left).to_range() | SpecifierSet(right).to_range()
        sets = u.to_specifier_sets()
        assert sets == tuple(SpecifierSet(e) for e in expected)

    def test_collapsed_adjacent_wildcards_split_into_per_family_sets(self) -> None:
        # ``==1.* | ==2.*`` collapses bounds to a single ``[1.dev0, 3.dev0)``
        # interval; ``to_specifier_sets`` decomposes that span back into the
        # per-family ``==V.*`` set chain rather than the dev0-tainted outer.
        u = SpecifierSet("==1.*").to_range() | SpecifierSet("==2.*").to_range()
        assert u.to_specifier_sets() == (
            SpecifierSet("==1.*"),
            SpecifierSet("==2.*"),
        )

    def test_multi_wildcard_filter_parity_with_union(self) -> None:
        # After the split, the union of each set's filter equals the range's
        # own filter (and the original union semantics), including the PEP
        # 440 pre-release buffering rule that ``>=V.dev0,<W,!=X.*`` lost.
        u = SpecifierSet("==1.*").to_range() | SpecifierSet("==3.*").to_range()
        sets = u.to_specifier_sets()
        assert sets is not None

        items = ["0.9", "1.0", "1.0a1", "1.5", "2.0", "3.0", "3.0a1", "4.0"]
        seen: list[str] = []
        for s in sets:
            for item in s.filter(items):
                if item not in seen:
                    seen.append(item)
        assert seen == list(u.filter(items))

        no_finals = ["1.0a1", "3.0a1"]
        seen_no_finals: list[str] = []
        for s in sets:
            for item in s.filter(no_finals):
                if item not in seen_no_finals:
                    seen_no_finals.append(item)
        assert seen_no_finals == list(u.filter(no_finals))

    def test_multi_wildcard_union_with_configured_true_keeps_per_family_split(
        self,
    ) -> None:
        # Explicit ``prereleases=True`` on both sources combines to True; the
        # split survives and each set inherits the configured policy.
        ss1 = SpecifierSet("==1.*", prereleases=True)
        ss2 = SpecifierSet("==3.*", prereleases=True)
        u = ss1.to_range() | ss2.to_range()
        sets = u.to_specifier_sets()
        assert sets == (
            SpecifierSet("==1.*", prereleases=True),
            SpecifierSet("==3.*", prereleases=True),
        )

    def test_collapsed_wildcards_with_not_equal_carve_out_distribute_excl(
        self,
    ) -> None:
        # ``[1.dev0, 3.dev0)`` collapses two adjacent wildcards; a ``!=1.5``
        # carve-out sits inside ``==1.*`` only. The split distributes the
        # exclusion to that family alone so the recovered sets still match
        # the original filter behaviour.
        a = SpecifierSet("==1.*").to_range() | SpecifierSet("==2.*").to_range()
        b = a & SpecifierSet("!=1.5").to_range()
        u = b | SpecifierSet("==9.*").to_range()
        assert u.to_specifier_sets() == (
            SpecifierSet("!=1.5,==1.*"),
            SpecifierSet("==2.*"),
            SpecifierSet("==9.*"),
        )

    def test_internal_not_equal_survives_wildcard_split(self) -> None:
        # A single ``==V.*`` family carrying its own ``!=V.5`` carve-out
        # keeps that exclusion as the split closes the group before the
        # cross-family ``!=X.*`` gap can reabsorb it.
        u = SpecifierSet("==1.*,!=1.5").to_range() | SpecifierSet("==3.*").to_range()
        assert u.to_specifier_sets() == (
            SpecifierSet("!=1.5,==1.*"),
            SpecifierSet("==3.*"),
        )


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
        # Complement preserves admit_arbitrary (False), so the reject
        # literal is dropped as redundant against the bounds. A reject
        # representation requires explicit construction via ``_build``.
        r = VersionRange._build(
            FULL_RANGE, reject=frozenset({"wat"}), admit_arbitrary=True
        )
        assert repr(r) == "<VersionRange '(-inf, +inf) \\\\ {wat}' arbitrary>"

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
        # PEP 440 has no disjunction operator, so admit-with-bounds is
        # unencodable; non-empty reject sets only arise via explicit
        # ``_build`` (complement preserves admit_arbitrary, which drops
        # the redundant reject literal).
        wat = VersionRange.from_specifier(Specifier("===wat"))
        rangelike = VersionRange.from_specifier_set(SpecifierSet(">=1.0,<2.0"))
        assert wat.union(rangelike).to_specifier_set() is None
        reject = VersionRange._build(
            FULL_RANGE, reject=frozenset({"wat"}), admit_arbitrary=True
        )
        assert reject.to_specifier_set() is None


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

    def test_full_range_bound_does_not_admit_literal(self) -> None:
        # >=0.dev0 canonicalizes to full bounds but, unlike SpecifierSet(""),
        # does not admit arbitrary strings. Its literal predicate must agree
        # with membership: "wat" is in neither.
        ge = VersionRange.from_specifier(Specifier(">=0.dev0"))
        assert "wat" not in ge
        assert not ge._matches_literal("wat")

    def test_intersection_literal_with_full_range_bound_excludes_literal(self) -> None:
        # ===wat & >=0.dev0: "wat" satisfies neither standard bound, so the
        # intersection drops it (regression: full bounds once admitted it).
        wat = VersionRange.from_specifier(Specifier("===wat"))
        ge = VersionRange.from_specifier(Specifier(">=0.dev0"))
        result = wat.intersection(ge)
        assert "wat" not in result
        assert result.is_empty

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

    def test_complement_of_admit_drops_redundant_reject(self) -> None:
        # Complement preserves admit_arbitrary (False here), so the
        # reject literal becomes redundant against the bounds (a
        # non-version string is rejected anyway) and ``_build`` drops it.
        # The complement is the "every PEP 440 version" predicate.
        wat = VersionRange.from_specifier(Specifier("===wat"))
        comp = wat.complement()
        assert comp._admit == frozenset()
        assert comp._reject == frozenset()
        assert comp._admit_arbitrary is False
        assert "wat" not in comp
        assert "1.0" in comp

    def test_double_complement_of_admit_loses_literal(self) -> None:
        # Under preservation, ``~(===wat)`` is "every version", and
        # complementing again yields the empty range: the non-version
        # literal is outside the PEP 440 universe ``complement`` works in.
        wat = VersionRange.from_specifier(Specifier("===wat"))
        assert wat.complement().complement() == VersionRange.empty()

    def test_intersection_admit_with_reject_is_empty(self) -> None:
        wat = VersionRange.from_specifier(Specifier("===wat"))
        not_wat = wat.complement()
        result = wat.intersection(not_wat)
        assert result.is_empty
        assert result._admit == frozenset()
        assert result._reject == frozenset()

    def test_partition_law_for_arbitrary(self) -> None:
        # Excluded middle on PEP 440 versions: ``===wat`` admits no
        # version, its complement admits every version, and the union
        # covers every version plus the ``wat`` literal. Non-version
        # garbage stays excluded, since ``complement`` preserves
        # ``_admit_arbitrary`` (False) rather than promoting it.
        wat = VersionRange.from_specifier(Specifier("===wat"))
        comp = wat.complement()
        assert wat.intersection(comp) == VersionRange.empty()
        u = wat.union(comp)
        assert u._admit_arbitrary is False
        assert "wat" in u
        for version in ("0", "1.0", "1!1.0", "1.0a1.dev0", "1.0+local"):
            assert version in u
        assert "garbage" not in u

    def test_union_keeps_literal_against_full_range_bound(self) -> None:
        # Superset law A subset of A|B: ===wat must survive union with a
        # standard operator that canonicalises to FULL_RANGE bounds.
        wat = VersionRange.from_specifier(Specifier("===wat"))
        ge = VersionRange.from_specifier(Specifier(">=0.dev0"))
        u = wat.union(ge)
        assert "wat" in u
        assert "1.0" in u

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
        # A reject set only survives when admit_arbitrary is True (the
        # bounds would otherwise admit the literal). Build directly,
        # since complement no longer reaches this shape.
        r = VersionRange._build(
            FULL_RANGE, reject=frozenset({"wat"}), admit_arbitrary=True
        )
        restored = pickle.loads(pickle.dumps(r))
        assert restored == r
        assert restored._reject == frozenset({"wat"})

    def test_intersect_complements_of_literals_is_full_versions(self) -> None:
        # Complement preserves admit_arbitrary (False), so each ``===``
        # literal's complement is the "every version" predicate.
        # Intersecting two such complements stays at the same predicate.
        a = VersionRange.from_specifier(Specifier("===wat"))
        b = VersionRange.from_specifier(Specifier("===foo"))
        r = ~a & ~b
        assert r._reject == frozenset()
        assert r._admit == frozenset()
        assert r._admit_arbitrary is False
        assert "wat" not in r
        assert "foo" not in r
        assert "1.0" in r
        assert r != VersionRange.full()

    def test_de_morgan_with_admit_literals(self) -> None:
        # ``~(a | b) == ~a & ~b`` for ``===`` literals: both sides drop
        # the non-version literals (complement preserves admit_arbitrary,
        # so the rejects are redundant against bounds) and collapse to
        # the "every version" predicate.
        a = VersionRange.from_specifier(Specifier("===wat"))
        b = VersionRange.from_specifier(Specifier("===foo"))
        assert ~(a | b) == (~a) & (~b)

    def test_involution_preserves_reject_through_admit_arbitrary_metadata(self) -> None:
        # On the empty bounds of ``~r`` the flag is metadata only, so
        # the swapped admit ``{"wat"}`` is not absorbed by ``_build``.
        # Complementing back swaps it into a reject under live FULL_RANGE
        # bounds, where the reject is needed, so ``~~r == r``.
        r = VersionRange._build(
            FULL_RANGE, reject=frozenset({"wat"}), admit_arbitrary=True
        )
        double = ~~r
        assert double._admit_arbitrary is True
        assert double._reject == frozenset({"wat"})
        assert "wat" not in double
        assert double == r


class TestArbitraryEdgeCases:
    """Admit/reject canonicalization and filter paths."""

    def test_build_resolves_admit_reject_overlap(self) -> None:
        # Reject wins over admit on overlap. With empty bounds and
        # ``admit_arbitrary=False`` the structural part already excludes
        # "wat", so the redundant reject is dropped.
        r = VersionRange._build((), admit=frozenset({"wat"}), reject=frozenset({"wat"}))
        assert "wat" not in r
        assert r._admit == frozenset()
        assert r._reject == frozenset()

    def test_build_keeps_reject_when_structural_admits(self) -> None:
        # ``admit_arbitrary=True`` admits "wat" structurally, so the reject
        # is the only record that excludes it.
        r = VersionRange._build(
            FULL_RANGE, reject=frozenset({"wat"}), admit_arbitrary=True
        )
        assert "wat" not in r
        assert r._reject == frozenset({"wat"})

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
        # A non-empty reject set only survives explicit construction now
        # (complement preserves admit_arbitrary and drops the redundant
        # rejection of a non-version literal). PEP 440 has no syntax for
        # excluding a literal string, so the encoder still returns None.
        r = VersionRange._build(
            FULL_RANGE, reject=frozenset({"wat"}), admit_arbitrary=True
        )
        assert r.to_specifier_sets() is None

    def test_to_specifier_sets_multiple_admit_splits_per_literal(self) -> None:
        # PEP 440 has no single-set form for OR over distinct ``===``
        # literals, but each literal encodes as its own ``===L`` piece.
        # Sorted output for determinism.
        a = VersionRange.from_specifier(Specifier("===wat"))
        b = VersionRange.from_specifier(Specifier("===other"))
        pieces = a.union(b).to_specifier_sets()
        assert pieces == (SpecifierSet("===other"), SpecifierSet("===wat"))

    def test_to_specifier_set_singular_multiple_admit_returns_none(self) -> None:
        # The singular form still rejects multi-piece shapes.
        a = VersionRange.from_specifier(Specifier("===wat"))
        b = VersionRange.from_specifier(Specifier("===other"))
        assert a.union(b).to_specifier_set() is None

    def test_to_specifier_sets_admit_plus_bounds_splits(self) -> None:
        # ``===wat | >=1.0`` has no single-set form but splits cleanly
        # into the admit literal and the bound group.
        admit = VersionRange.from_specifier(Specifier("===wat"))
        bounds = VersionRange.from_specifier(Specifier(">=1.0"))
        pieces = admit.union(bounds).to_specifier_sets()
        assert pieces == (SpecifierSet("===wat"), SpecifierSet(">=1.0"))

    def test_to_specifier_set_singular_admit_plus_bounds_returns_none(self) -> None:
        # The singular form keeps the "single-piece or None" contract.
        admit = VersionRange.from_specifier(Specifier("===wat"))
        bounds = VersionRange.from_specifier(Specifier(">=1.0"))
        assert admit.union(bounds).to_specifier_set() is None

    def test_to_specifier_sets_admit_plus_disjoint_bound_groups(self) -> None:
        # Admit literal alongside two disjoint bound groups: each becomes
        # its own piece in sorted-admit-then-bound-group order.
        admit = VersionRange.from_specifier(Specifier("===wat"))
        a = VersionRange.from_specifier_set(SpecifierSet(">=1.0,<2.0"))
        b = VersionRange.from_specifier_set(SpecifierSet(">=3.0,<4.0"))
        pieces = admit.union(a).union(b).to_specifier_sets()
        assert pieces is not None
        assert {str(p) for p in pieces} == {
            "===wat",
            "<2.0,>=1.0",
            "<4.0,>=3.0",
        }
        # Admit pieces precede bound groups in the deterministic order.
        assert str(pieces[0]) == "===wat"

    def test_to_specifier_sets_admit_arbitrary_with_narrowed_bounds(self) -> None:
        # A constructed range with arbitrary-string admission and narrowed
        # bounds has no PEP 440 form. Algebra cannot reach this shape.
        interval = (
            LowerBound(Version("1.0"), inclusive=True),
            UpperBound(Version("2.0"), inclusive=False),
        )
        r = VersionRange._build((interval,), admit_arbitrary=True)
        assert r.to_specifier_sets() is None
        assert r.to_specifier_set() is None

    def test_to_specifier_sets_admit_plus_bounds_round_trips(self) -> None:
        # Union of the emitted pieces (via from_specifier_set) must reproduce
        # the original range.
        original = VersionRange.from_specifier(
            Specifier("===wat")
        ) | VersionRange.from_specifier_set(SpecifierSet(">=1.0,<2.0"))
        pieces = original.to_specifier_sets()
        assert pieces is not None
        rebuilt = VersionRange.empty()
        for piece in pieces:
            rebuilt = rebuilt | VersionRange.from_specifier_set(piece)
        assert rebuilt == original

    def test_is_prerelease_only_empty_is_false(self) -> None:
        assert VersionRange.empty().is_prerelease_only is False

    def test_is_prerelease_only_with_reject_is_false(self) -> None:
        # A reject literal forces ``is_prerelease_only`` to False even
        # when bounds and admit literals are pre-release only. Built
        # explicitly: complement preserves admit_arbitrary so it no
        # longer produces a reject through algebra alone.
        bounds = SpecifierSet(">=1.0a1,<1.0").to_range()._bounds
        r = VersionRange._build(bounds, reject=frozenset({"wat"}), admit_arbitrary=True)
        assert r.is_prerelease_only is False

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
    filters like the composed specifier. ``&`` / ``|`` require both
    operands to share a configured pre-release policy and propagate it;
    ``~`` preserves it.
    """

    # A final release and a pre-release; both sit inside every range below.
    SAMPLE_VERSIONS = (Version("1.0"), Version("2.0a1"))

    @staticmethod
    def _tagged_ranges() -> tuple[VersionRange, VersionRange, VersionRange]:
        """Three ranges that contain both SAMPLE_VERSIONS, one per configured
        policy: explicit True, autodetect None, and explicit False."""
        true_tag = SpecifierSet("<3.0", prereleases=True).to_range()
        none_tag = SpecifierSet("<3.0").to_range()
        false_tag = SpecifierSet("<3.0", prereleases=False).to_range()
        assert true_tag._prereleases_configured is True
        assert none_tag._prereleases_configured is None
        assert false_tag._prereleases_configured is False
        return true_tag, none_tag, false_tag

    def test_full_range_is_identity_for_filtering_under_none(self) -> None:
        # ``full()`` is configured None, so it only composes with another
        # None-configured operand under the strict same-policy rule.
        full = VersionRange.full()
        none_tag = SpecifierSet("<3.0").to_range()
        expected = list(none_tag.filter(self.SAMPLE_VERSIONS))
        assert list((none_tag & full).filter(self.SAMPLE_VERSIONS)) == expected
        assert list((full & none_tag).filter(self.SAMPLE_VERSIONS)) == expected

    def test_intersection_propagates_shared_policy(self) -> None:
        true_tag, none_tag, false_tag = self._tagged_ranges()
        # Same-policy pairs succeed; the result inherits the shared tag.
        assert (true_tag & true_tag)._prereleases_configured is True
        assert (none_tag & none_tag)._prereleases_configured is None
        assert (false_tag & false_tag)._prereleases_configured is False

    def test_intersection_both_none_keeps_autodetect_true(self) -> None:
        # Both operands configured None, but one autodetects True. The
        # configured tag stays None on the result while ``_prereleases``
        # falls back to the autodetected True.
        auto_true = SpecifierSet(">=1.0a1").to_range()
        default = SpecifierSet("<3.0").to_range()
        combined = auto_true & default
        assert combined._prereleases_configured is None
        assert combined._prereleases is True

    def test_union_propagates_shared_policy(self) -> None:
        true_tag, none_tag, false_tag = self._tagged_ranges()
        assert (true_tag | true_tag)._prereleases_configured is True
        assert (none_tag | none_tag)._prereleases_configured is None
        assert (false_tag | false_tag)._prereleases_configured is False

    def test_complement_preserves_prereleases_tag(self) -> None:
        # Complement stays in the PEP 440 universe, so the configured
        # policy and resolved tag both carry over unchanged.
        for r in self._tagged_ranges():
            inv = r.complement()
            assert inv._prereleases_configured == r._prereleases_configured
            assert inv._prereleases == r._prereleases

    @pytest.mark.parametrize(
        "policy",
        [None, True, False],
    )
    def test_complement_preserves_each_policy(self, policy: bool | None) -> None:
        # Regression: ``~`` must keep ``_prereleases_configured`` for every
        # value of the three-state policy.
        r = SpecifierSet("<3.0", prereleases=policy).to_range()
        assert r._prereleases_configured is policy
        assert r.complement()._prereleases_configured is policy

    @pytest.mark.parametrize(
        ("a", "b"),
        [
            (SpecifierSet(">=1.0a1"), SpecifierSet("<3.0")),
            (SpecifierSet(">=1.0"), SpecifierSet("<3.0")),
            (SpecifierSet(">=1.0a1"), SpecifierSet(">=1.0a1")),
            (SpecifierSet(">=1.0a1,<3.0"), SpecifierSet("")),
            (SpecifierSet(""), SpecifierSet(">=1.0a1")),
            (SpecifierSet(">=1.0"), SpecifierSet(">=1.0a1")),
            # Same explicit policy on both sides.
            (
                SpecifierSet(">=1.0", prereleases=False),
                SpecifierSet("<3.0", prereleases=False),
            ),
            (
                SpecifierSet(">=1.0", prereleases=True),
                SpecifierSet("<3.0", prereleases=True),
            ),
        ],
    )
    def test_intersection_is_a_homomorphism(
        self, a: SpecifierSet, b: SpecifierSet
    ) -> None:
        """``(a.to_range() & b.to_range()).filter`` equals
        ``(a & b).to_range().filter``."""
        composed_ranges = list(
            (a.to_range() & b.to_range()).filter(self.SAMPLE_VERSIONS)
        )
        composed_set = list((a & b).to_range().filter(self.SAMPLE_VERSIONS))
        assert composed_ranges == composed_set

    @pytest.mark.parametrize(
        ("a", "b"),
        [
            (Specifier(">=1.0a1"), Specifier("<3.0")),
            (
                Specifier(">=1.0", prereleases=False),
                Specifier("<3.0", prereleases=False),
            ),
        ],
    )
    def test_specifier_intersection_is_a_homomorphism(
        self, a: Specifier, b: Specifier
    ) -> None:
        """Intersecting two single-specifier ranges filters like keeping
        the versions each specifier accepts under its shared policy."""
        composed_ranges = list(
            (a.to_range() & b.to_range()).filter(self.SAMPLE_VERSIONS)
        )
        oracle = [v for v in self.SAMPLE_VERSIONS if a.contains(v) and b.contains(v)]
        assert composed_ranges == oracle

    @pytest.mark.parametrize(
        "policy",
        [None, True, False],
    )
    def test_intersection_carries_configured_override(
        self, policy: bool | None
    ) -> None:
        # Same-policy operands keep the policy on the result.
        a = SpecifierSet(">=1.0", prereleases=policy).to_range()
        b = SpecifierSet("<3.0", prereleases=policy).to_range()
        assert (a & b)._prereleases_configured is policy

    @pytest.mark.parametrize(
        ("policy_a", "policy_b"),
        [
            (None, True),
            (None, False),
            (True, None),
            (False, None),
            (True, False),
            (False, True),
        ],
    )
    def test_intersection_rejects_mismatched_policies(
        self, policy_a: bool | None, policy_b: bool | None
    ) -> None:
        a = SpecifierSet(">=1.0", prereleases=policy_a).to_range()
        b = SpecifierSet("<3.0", prereleases=policy_b).to_range()
        message = "different pre-release policies"
        with pytest.raises(ValueError, match=message):
            a & b
        with pytest.raises(ValueError, match=message):
            a.intersection(b)

    @pytest.mark.parametrize(
        ("policy_a", "policy_b"),
        [
            (None, True),
            (None, False),
            (True, None),
            (False, None),
            (True, False),
            (False, True),
        ],
    )
    def test_union_rejects_mismatched_policies(
        self, policy_a: bool | None, policy_b: bool | None
    ) -> None:
        a = SpecifierSet(">=1.0", prereleases=policy_a).to_range()
        b = SpecifierSet("<3.0", prereleases=policy_b).to_range()
        message = "different pre-release policies"
        with pytest.raises(ValueError, match=message):
            a | b
        with pytest.raises(ValueError, match=message):
            a.union(b)

    def test_mismatch_error_names_both_policies(self) -> None:
        # The message must spell out the two policies so callers can
        # diagnose without inspecting the operands.
        a = SpecifierSet(">=1.0", prereleases=True).to_range()
        b = SpecifierSet("<3.0", prereleases=False).to_range()
        with pytest.raises(ValueError, match=r"True.*False|False.*True"):
            a & b

    @pytest.mark.parametrize(
        "policy",
        [None, True, False],
    )
    def test_union_populates_configured_override(self, policy: bool | None) -> None:
        a = SpecifierSet(">=1.0", prereleases=policy).to_range()
        b = SpecifierSet("<3.0", prereleases=policy).to_range()
        assert (a | b)._prereleases_configured is policy

    def test_union_contains_and_filter_agree(self) -> None:
        # ``contains`` reads ``_prereleases_configured`` and ``filter`` reads
        # ``_prereleases``; union must keep the two slots in step, just like
        # intersection, so the same range answers both APIs consistently.
        r1 = SpecifierSet(">=1.0a1").to_range()
        r2 = SpecifierSet("<3.0").to_range()
        union = r1 | r2
        assert ("1.5a1" in union) == bool(list(union.filter(["1.5a1"])))

    def test_complement_preserves_configured_override(self) -> None:
        explicit_false = SpecifierSet("<3.0", prereleases=False).to_range()
        assert explicit_false.complement()._prereleases_configured is False

    def test_from_specifier_set_accepts_mixed_prereleases_specs(self) -> None:
        # ``SpecifierSet`` allows an iterable of specifiers with conflicting
        # per-spec ``prereleases`` overrides (the set-level tag wins). The
        # ``===`` slow path inside ``from_specifier_set`` folds via
        # ``intersection``, which now raises on any mismatched configured
        # policy, so the fold must neutralize the per-spec tags.
        s1 = Specifier(">=1.0", prereleases=True)
        s2 = Specifier("===wat", prereleases=False)
        ss = SpecifierSet([s1, s2])
        r = VersionRange.from_specifier_set(ss)
        # The set-level configured override (None here) is what ends up on
        # the range, not either per-spec tag.
        assert r._prereleases_configured is None

    @pytest.mark.parametrize(
        "policy",
        [None, True, False],
    )
    def test_union_with_full_canonicalizes_policy(self, policy: bool | None) -> None:
        # ``full()`` is configured None. Under the strict rule it can only
        # compose with a None-configured operand; the union still collapses
        # to the canonical ``full()`` in both operand orders.
        if policy is None:
            r = SpecifierSet(">=1.0").to_range()
        else:
            r = SpecifierSet(">=1.0", prereleases=policy).to_range()
            with pytest.raises(ValueError, match="different pre-release policies"):
                r | VersionRange.full()
            return
        full = VersionRange.full()
        assert r | full == full
        assert full | r == full
        assert (r | full)._prereleases_configured is None
        assert (full | r)._prereleases_configured is None

    @pytest.mark.parametrize("policy", [True, False])
    def test_union_of_configured_arbitrary_ranges_preserves_policy(
        self, policy: bool
    ) -> None:
        # ``SpecifierSet("", prereleases=policy).to_range()`` is shaped like
        # ``full()`` but carries an explicit configured tag. Two such operands
        # share the same tag so policy compat passes; the union must keep the
        # configured tag instead of collapsing it to the autodetect default.
        r = SpecifierSet("", prereleases=policy).to_range()
        assert r._admit_arbitrary is True
        assert r._prereleases_configured is policy

        joined = r | r
        assert joined._admit_arbitrary is True
        assert joined._prereleases_configured is policy
        assert joined._prereleases is policy

        # The result must round-trip back to the same SpecifierSet.
        assert joined.to_specifier_set() == SpecifierSet("", prereleases=policy)

    def test_union_with_full_associative_canonicalization(self) -> None:
        # Reaching full() anywhere in a chain still canonicalizes the policy,
        # provided every operand shares the configured-None policy.
        r = SpecifierSet(">=1.0").to_range()
        s = SpecifierSet("<5.0").to_range()
        full = VersionRange.full()
        assert (r | s) | full == full
        assert r | (s | full) == full


class TestPrereleaseHomomorphismDifferential:
    """Brute-force the intersection homomorphism across a grid of
    override states, using SpecifierSet.filter as the authoritative oracle.
    """

    POOL = (
        Version("0.5"),
        Version("1.0"),
        Version("1.0a1"),
        Version("2.0a1"),
        Version("2.5"),
        Version("3.0b1"),
    )

    @staticmethod
    def _set_operands() -> list[SpecifierSet]:
        # Override state varies across: full (autodetect None), autodetect
        # via a pre-release version (configured None), autodetect None,
        # explicit True, and explicit False.
        return [
            SpecifierSet(""),
            SpecifierSet(">=1.0a1"),
            SpecifierSet(">=1.0"),
            SpecifierSet("<3.0"),
            SpecifierSet("<3.0", prereleases=True),
            SpecifierSet("<3.0", prereleases=False),
            SpecifierSet(">=1.0a1", prereleases=False),
            SpecifierSet(">=1.0a1", prereleases=True),
            SpecifierSet(">=0.5,<2.5"),
            SpecifierSet(">=1.0a1,<2.5", prereleases=True),
        ]

    def test_set_intersection_homomorphism_grid(self) -> None:
        operands = self._set_operands()
        divergences: list[str] = []
        pairs = 0
        for a in operands:
            for b in operands:
                try:
                    combined = a & b
                except ValueError:
                    # ``SpecifierSet.__and__`` raises on True/False
                    # configured conflicts; no oracle exists, so skip.
                    continue
                ra = a.to_range()
                rb = b.to_range()
                if ra._prereleases_configured != rb._prereleases_configured:
                    # ``VersionRange`` now demands matching policies even
                    # when ``SpecifierSet.__and__`` would not, so skip the
                    # range-side comparison; the set-side fold below still
                    # covers ``SpecifierSet`` itself.
                    with pytest.raises(ValueError, match="different pre-release"):
                        ra & rb
                    continue
                pairs += 1
                via_ranges = list((ra & rb).filter(self.POOL, prereleases=None))
                via_set_range = list(
                    combined.to_range().filter(self.POOL, prereleases=None)
                )
                via_set = list(combined.filter(self.POOL))
                if not (via_ranges == via_set_range == via_set):
                    divergences.append(
                        f"{a!r} & {b!r}: {via_ranges} {via_set_range} {via_set}"
                    )
        assert divergences == [], divergences
        assert pairs > 0


class TestMinVersionCanonicalization:
    """The exclusive-upper-at-min round-trip bug and its canonicalization.

    ``(-inf, 0.dev0)`` exclusive-upper is semantically empty because
    ``0.dev0`` is the smallest PEP 440 version, so nothing is below it.
    The empty guard and the bottom-anchored-lower canonicalization keep
    set algebra closed under round-tripping.
    """

    def test_original_repro_complement_is_empty_and_round_trips(self) -> None:
        # ``>=0.dev0`` covers every version and rejects non-version
        # strings; complement preserves the admit_arbitrary flag, so
        # the result is the empty range, which encodes as ``<0``.
        r = SpecifierSet(">=0.dev0").to_range().complement()
        assert r.is_empty is True
        spec_set = r.to_specifier_set()
        assert spec_set == SpecifierSet("<0")
        back = VersionRange.from_specifier_set(spec_set)
        assert back == r

    def test_range_is_empty_exclusive_upper_at_min(self) -> None:
        upper = UpperBound(Version("0.dev0"), inclusive=False)
        assert range_is_empty(NEG_INF, upper) is True

    def test_range_is_empty_inclusive_upper_at_min_is_nonempty(self) -> None:
        # ``<=0.dev0`` is the singleton {0.dev0}, which is NOT empty.
        upper = UpperBound(Version("0.dev0"), inclusive=True)
        assert range_is_empty(NEG_INF, upper) is False

    def test_canonical_lower_collapses_inclusive_min_to_neg_inf(self) -> None:
        at_min = LowerBound(Version("0.dev0"), inclusive=True)
        assert canonical_lower(at_min) == NEG_INF
        # An exclusive lower at min, or a higher lower, is left untouched.
        higher = LowerBound(Version("1.0"), inclusive=True)
        assert canonical_lower(higher) == higher
        exclusive_min = LowerBound(Version("0.dev0"), inclusive=False)
        assert canonical_lower(exclusive_min) == exclusive_min

    @pytest.mark.parametrize(
        "spec",
        ["==0.*", "<1", "~=0.0", ">=1.0", "<2.0", "!=1.5", "==1.0"],
    )
    def test_double_complement_structural_identity(self, spec: str) -> None:
        r = SpecifierSet(spec).to_range()
        assert r.complement().complement() == r

    def test_double_complement_preserves_ge_dev0(self) -> None:
        # ``>=0.dev0`` canonicalizes to FULL_RANGE bounds but rejects
        # arbitrary strings. Complement preserves the flag, so the
        # intermediate is the empty range; complementing back restores
        # the original (and stays distinct from ``full()``, which does
        # admit arbitrary strings).
        r = SpecifierSet(">=0.dev0").to_range()
        round_tripped = r.complement().complement()
        assert round_tripped == r
        assert round_tripped != VersionRange.full()
        assert "garbage" not in round_tripped


class TestArbitraryAdmissionFlag:
    """Arbitrary-string admission must be keyed on the explicit
    ``_admit_arbitrary`` flag, not on ``_bounds == FULL_RANGE``.

    Canonicalization makes ``>=0.dev0`` reach the full-range bounds, but it
    must NOT inherit the ``SpecifierSet("")`` arbitrary-string behavior.
    """

    def test_garbage_not_in_ge_dev0_range(self) -> None:
        assert "garbage" not in Specifier(">=0.dev0").to_range()
        assert "garbage" not in SpecifierSet(">=0.dev0").to_range()

    def test_ge_dev0_filter_mirrors_specifier(self) -> None:
        items = ["garbage", "1.0"]
        assert list(Specifier(">=0.dev0").to_range().filter(items)) == list(
            Specifier(">=0.dev0").filter(items)
        )
        assert list(SpecifierSet(">=0.dev0").to_range().filter(items)) == list(
            SpecifierSet(">=0.dev0").filter(items)
        )

    def test_empty_specifier_set_still_admits_arbitrary(self) -> None:
        assert "garbage" in SpecifierSet("").to_range()
        assert "garbage" in VersionRange.full()

    def test_full_and_empty_complement_laws(self) -> None:
        # Complement preserves the flag as metadata: ``~empty()`` is full
        # bounds without arbitrary admission (distinct from ``full()``),
        # and ``~full()`` is empty bounds carrying the flag
        # (membership-empty, distinct from ``empty()``).
        empty_comp = VersionRange.empty().complement()
        assert empty_comp != VersionRange.full()
        assert empty_comp._admit_arbitrary is False
        assert "garbage" not in empty_comp
        assert "1.0" in empty_comp
        full_comp = VersionRange.full().complement()
        assert full_comp != VersionRange.empty()
        assert full_comp._admit_arbitrary is True
        assert "garbage" not in full_comp
        assert "1.0" not in full_comp
        assert full_comp.is_empty

    @pytest.mark.parametrize(
        "spec", [">=0.dev0", ">=0", "==0.*", "~=0.0", "<1", ">=1.0"]
    )
    @pytest.mark.parametrize("prereleases", [None, True, False])
    def test_filter_and_membership_mirror_specifier(
        self, spec: str, prereleases: bool | None
    ) -> None:
        items = ["garbage", "junk", "0.dev0", "0", "0.5", "1.0", "2.0a1", "2.0"]
        spec_obj = Specifier(spec)
        set_obj = SpecifierSet(spec)

        assert list(spec_obj.to_range().filter(items, prereleases=prereleases)) == list(
            spec_obj.filter(items, prereleases=prereleases)
        )
        assert list(set_obj.to_range().filter(items, prereleases=prereleases)) == list(
            set_obj.filter(items, prereleases=prereleases)
        )
        for item in items:
            assert (item in spec_obj.to_range()) == spec_obj.contains(
                item, prereleases=True
            )
            assert (item in set_obj.to_range()) == set_obj.contains(
                item, prereleases=True
            )

    def test_admit_arbitrary_eq_distinguishes_flag(self) -> None:
        # full() admits arbitrary; a >=0.dev0 range does not. The flag
        # changes what ``in`` accepts, so equality must reflect it even
        # though both share FULL_RANGE bounds.
        full = VersionRange.full()
        ge = Specifier(">=0.dev0").to_range()
        assert ge != full
        assert hash(ge) != hash(full)

    def test_pickle_preserves_admit_arbitrary(self) -> None:
        for r in (VersionRange.full(), SpecifierSet("").to_range()):
            restored = pickle.loads(pickle.dumps(r))
            assert restored._admit_arbitrary is True
            assert ("garbage" in restored) == ("garbage" in r)
            assert list(restored.filter(["garbage"])) == list(r.filter(["garbage"]))

        ge = Specifier(">=0.dev0").to_range()
        restored = pickle.loads(pickle.dumps(ge))
        assert restored._admit_arbitrary is False
        assert "garbage" not in restored
        assert list(restored.filter(["garbage", "1.0"])) == list(
            ge.filter(["garbage", "1.0"])
        )


class TestPicklePreservesPolicy:
    """Pickle must round-trip the prerelease policy slots and behavior."""

    @staticmethod
    def _cases() -> list[VersionRange]:
        # One range per configured policy, plus an autodetect-True range
        # and a same-policy combination to exercise composed slots.
        explicit_false = SpecifierSet("<3.0", prereleases=False).to_range()
        explicit_true = SpecifierSet("<3.0", prereleases=True).to_range()
        auto_true = Specifier(">=1.0a1").to_range()
        none_other = Specifier("<3.0").to_range()
        return [
            auto_true,
            explicit_false,
            explicit_true,
            auto_true & none_other,
            VersionRange.empty(),
            VersionRange.full(),
        ]

    def test_round_trip_preserves_policy_slots(self) -> None:
        items = ["1.0", "2.0a1", "2.5"]
        for r in self._cases():
            restored = pickle.loads(pickle.dumps(r))
            assert restored._prereleases == r._prereleases
            assert restored._prereleases_configured == r._prereleases_configured
            assert restored._admit_arbitrary == r._admit_arbitrary
            assert list(restored.filter(items)) == list(r.filter(items))

    def test_eq_and_hash_distinguish_configured_override(self) -> None:
        # Two ranges differing only in _prereleases_configured accept
        # different items under ``in`` (the explicit-False range rejects
        # pre-releases), so equality and hash must reflect that.
        base = SpecifierSet("<3.0").to_range()
        other = SpecifierSet("<3.0", prereleases=False).to_range()
        assert base._prereleases_configured != other._prereleases_configured
        assert base != other
        assert hash(base) != hash(other)


class TestAdmitArbitraryPropagation:
    """Brute-force the ``_admit_arbitrary`` lattice across &/|/~.

    Intersection ANDs, union ORs, complement preserves. Membership of
    ``garbage`` fires only when the flag is paired with ``FULL_RANGE``
    bounds; on narrower bounds it rides along as metadata.
    """

    @staticmethod
    def _samples() -> dict[str, VersionRange]:
        return {
            "full": VersionRange.full(),
            "empty": VersionRange.empty(),
            "ge1": Specifier(">=1.0").to_range(),
            "wat": VersionRange.from_specifier(Specifier("===wat")),
            "ge_dev0": Specifier(">=0.dev0").to_range(),
        }

    @staticmethod
    def _arbitrary_fires(r: VersionRange) -> bool:
        return r._admit_arbitrary and r._bounds == FULL_RANGE

    def test_garbage_membership_matches_live_arbitrary(self) -> None:
        for r in self._samples().values():
            assert ("garbage" in r) == self._arbitrary_fires(r)

    def test_pairwise_set_algebra_admit_semantics(self) -> None:
        samples = self._samples()
        for a in samples.values():
            for b in samples.values():
                inter = a & b
                assert inter._admit_arbitrary == (
                    a._admit_arbitrary and b._admit_arbitrary
                )
                assert ("garbage" in inter) == self._arbitrary_fires(inter)

                uni = a | b
                assert uni._admit_arbitrary == (
                    a._admit_arbitrary or b._admit_arbitrary
                )
                assert ("garbage" in uni) == self._arbitrary_fires(uni)

            comp = a.complement()
            assert comp._admit_arbitrary == a._admit_arbitrary
            assert ("garbage" in comp) == self._arbitrary_fires(comp)


class TestSetLaws:
    """Boolean-algebra laws over PEP 440 ranges.

    Complement preserves ``_admit_arbitrary``, so De Morgan, excluded
    middle, and contradiction hold structurally across the PEP 440
    universe (every sample whose flag is False) for bound-only ranges.
    ``full()`` crosses the universe boundary: only the involution and
    identity laws hold structurally for it. ``===L`` literals also
    degenerate under complement, since the non-version literal sits
    outside the PEP 440 universe (covered by the carve-out tests above).
    """

    @staticmethod
    def _pep440_samples() -> dict[str, VersionRange]:
        return {
            "empty": VersionRange.empty(),
            "ge1": SpecifierSet(">=1.0").to_range(),
            "lt3": SpecifierSet("<3.0").to_range(),
            "ge1_lt2": SpecifierSet(">=1.0,<2.0").to_range(),
            "ne15": SpecifierSet("!=1.5").to_range(),
            "ge0_dev0": SpecifierSet(">=0.dev0").to_range(),
            "singleton_1": VersionRange.singleton("1.0"),
        }

    @staticmethod
    def _all_samples() -> dict[str, VersionRange]:
        return {"full": VersionRange.full(), **TestSetLaws._pep440_samples()}

    VERSION_PROBES = ("0", "1.0", "1.5", "2.0", "1.0a1", "1!1.0", "1.0+local")
    NON_VERSION_PROBES = ("wat", "garbage")
    PROBES = VERSION_PROBES + NON_VERSION_PROBES

    def _agree(self, a: VersionRange, b: VersionRange) -> None:
        assert a == b
        for p in self.PROBES:
            assert (p in a) == (p in b), p

    def test_double_negation(self) -> None:
        for r in self._all_samples().values():
            self._agree(r.complement().complement(), r)

    def test_de_morgan_intersection(self) -> None:
        samples = list(self._pep440_samples().values())
        for a in samples:
            for b in samples:
                self._agree(~(a & b), (~a) | (~b))

    def test_de_morgan_union(self) -> None:
        samples = list(self._pep440_samples().values())
        for a in samples:
            for b in samples:
                self._agree(~(a | b), (~a) & (~b))

    def test_excluded_middle_versions(self) -> None:
        for r in self._pep440_samples().values():
            u = r | ~r
            assert u._admit_arbitrary is False
            for p in self.VERSION_PROBES:
                assert p in u, p
            for p in self.NON_VERSION_PROBES:
                assert p not in u, p

    def test_contradiction(self) -> None:
        for r in self._pep440_samples().values():
            i = r & ~r
            assert i.is_empty
            assert not i._admit_arbitrary
            for p in self.PROBES:
                assert p not in i, p

    def test_intersection_with_full_is_self(self) -> None:
        full = VersionRange.full()
        for r in self._all_samples().values():
            self._agree(r & full, r)
            self._agree(full & r, r)

    def test_union_with_empty_is_self(self) -> None:
        empty = VersionRange.empty()
        for r in self._all_samples().values():
            self._agree(r | empty, r)
            self._agree(empty | r, r)

    def test_complement_of_full_keeps_arbitrary_flag(self) -> None:
        # ``~full()`` keeps ``_admit_arbitrary`` as metadata but matches
        # nothing. Distinct from ``empty()`` because the flag rides
        # along for a later widening union.
        comp = VersionRange.full().complement()
        assert comp._admit_arbitrary is True
        assert not comp._bounds
        assert "garbage" not in comp
        assert "1.0" not in comp
        assert comp.is_empty
        assert comp != VersionRange.empty()
        assert comp == VersionRange.empty(admit_arbitrary=True)

    def test_complement_of_empty_preserves_no_arbitrary(self) -> None:
        # ``~empty()`` reaches FULL_RANGE bounds but inherits the False
        # flag, so it stays distinct from ``full()``.
        comp = VersionRange.empty().complement()
        assert comp._admit_arbitrary is False
        assert comp._bounds == VersionRange.full()._bounds
        assert "garbage" not in comp
        assert "1.0" in comp
        assert comp != VersionRange.full()


class TestUnsatisfiabilityAfterCanonicalization:
    """Canonicalization must not break the prerelease-only check, which
    drives ``SpecifierSet.is_unsatisfiable`` under ``prereleases=False``.
    """

    def test_eq_dev0_unsatisfiable_with_no_pre(self) -> None:
        assert SpecifierSet("==0.dev0", prereleases=False).is_unsatisfiable() is True

    def test_eq_0_0_dev0_unsatisfiable_with_no_pre(self) -> None:
        assert SpecifierSet("==0.0.dev0", prereleases=False).is_unsatisfiable() is True

    def test_satisfiable_controls(self) -> None:
        assert SpecifierSet("<0.5", prereleases=False).is_unsatisfiable() is False
        assert SpecifierSet(">=0.dev0", prereleases=False).is_unsatisfiable() is False

    def test_prior_high_fix_still_holds(self) -> None:
        unsat = SpecifierSet(">1.0a1.post2,<1.0.post0", prereleases=False)
        assert unsat.is_unsatisfiable() is False
        assert unsat.contains("1.0") is True

    def test_lowest_release_at_or_above_none_returns_zero(self) -> None:
        assert _lowest_release_at_or_above(None) == Version("0")


class TestAfterLocalsSuccessorDev:
    """``_after_locals_successor`` must increment ``dev`` for dev versions.

    The old V.post(N+1).dev0 formula overshot for any V with a dev segment:
    ``1.0.dev0`` mapped to ``1.0.post0.dev0`` (above ``1.0.dev5``), making
    ``!=1.0.dev0,<1.0.dev5`` look empty even though ``1.0.dev3`` fits both
    constituent specifiers.
    """

    def test_set_contains_agrees_with_constituents(self) -> None:
        ss = SpecifierSet("!=1.0.dev0,<1.0.dev5")
        assert ss.contains("1.0.dev3", prereleases=True) is True
        assert Specifier("!=1.0.dev0").contains("1.0.dev3", prereleases=True) is True
        assert Specifier("<1.0.dev5").contains("1.0.dev3", prereleases=True) is True

    @pytest.mark.parametrize(
        ("version", "expected"),
        [
            ("1.0.dev0", "1.0.dev1"),
            ("1.0a1.dev0", "1.0a1.dev1"),
            ("1.0.post1.dev0", "1.0.post1.dev1"),
            ("1.0.dev0+local", "1.0.dev1"),
            ("1.0", "1.0.post0.dev0"),
            ("1.0a1", "1.0a1.post0.dev0"),
            ("1.0.post1", "1.0.post2.dev0"),
        ],
    )
    def test_successor_table(self, version: str, expected: str) -> None:
        assert _after_locals_successor(Version(version)) == Version(expected)


class TestFilterSignatureParity:
    """``VersionRange.filter`` mirrors ``SpecifierSet.filter`` positionally.

    Both accept ``(iterable, prereleases=None, key=None)`` so a positional
    swap-in between the two does not raise.
    """

    def test_positional_prereleases_false_matches_specifier_set(self) -> None:
        ss = SpecifierSet(">=1.0")
        items = ["1.5", "2.0a1"]
        assert list(ss.filter(items, False)) == list(ss.to_range().filter(items, False))

    def test_positional_prereleases_true_matches_specifier_set(self) -> None:
        ss = SpecifierSet(">=1.0")
        items = ["1.5", "2.0a1"]
        assert list(ss.filter(items, True)) == list(ss.to_range().filter(items, True))

    def test_positional_key_callable(self) -> None:
        r = VersionRange.from_specifier_set(SpecifierSet(">=1.0,<2.0"))
        items = [{"v": "0.9"}, {"v": "1.5"}, {"v": "2.0"}]
        assert list(r.filter(items, None, lambda x: x["v"])) == [{"v": "1.5"}]

    def test_specifier_filter_positional_parity(self) -> None:
        spec = Specifier(">=1.0")
        items = ["1.5", "2.0a1"]
        assert list(spec.filter(items, False)) == list(
            spec.to_range().filter(items, False)
        )


# Mixed final and pre-release versions shared by the round-trip and key tests.
_FILTER_POOL = [
    Version("0.5"),
    Version("1.0"),
    Version("1.0a1"),
    Version("1.0.dev0"),
    Version("1.5"),
    Version("1.5a1"),
    Version("2.0"),
    Version("2.0a1"),
    Version("3.0"),
    Version("3.0a1"),
    Version("3.5"),
    Version("4.0"),
    Version("1!1.0"),
]


def _union_filter(
    sets: tuple[SpecifierSet, ...],
    pool: list[Version],
) -> list[Version]:
    """Filter pool through each set; preserve order, drop duplicates."""
    seen: list[Version] = []
    for s in sets:
        for v in s.filter(pool):
            if v not in seen:
                seen.append(v)
    return seen


class TestToSpecifierSetFilterEquivalence:
    """``to_specifier_set``/``to_specifier_sets`` reproduces ``filter`` output.

    Pins the source range's configured policy and asserts the recovered
    set (or the union of recovered sets) admits the same pool members in
    the same order as the source range under autodetect filtering.
    """

    SPEC_STRINGS: ClassVar[list[str]] = [
        "==1.0",
        ">=1.0,<2.0",
        "!=1.5",
        "==1.*",
        "!=1.*",
        "~=1.0",
        ">=1.0,<2.0,!=1.5",
        "===1.5",
    ]

    @pytest.mark.parametrize("spec_str", SPEC_STRINGS)
    @pytest.mark.parametrize("policy", [None, True, False])
    def test_single_set_round_trip_filter_equivalent(
        self, spec_str: str, policy: bool | None
    ) -> None:
        ss = SpecifierSet(spec_str, prereleases=policy)
        r = ss.to_range()
        rt = r.to_specifier_set()
        assert rt is not None, f"{spec_str!r} (P={policy}) failed to re-encode"
        assert list(r.filter(_FILTER_POOL)) == list(rt.filter(_FILTER_POOL))

    @pytest.mark.parametrize("policy", [None, True, False])
    def test_disjoint_wildcard_union_filter_equivalent(
        self, policy: bool | None
    ) -> None:
        # ``==1.* | ==3.*`` only round-trips via ``to_specifier_sets``;
        # the single-set form is ``None``.
        ss1 = SpecifierSet("==1.*", prereleases=policy)
        ss2 = SpecifierSet("==3.*", prereleases=policy)
        r = ss1.to_range() | ss2.to_range()
        rt_list = r.to_specifier_sets()
        assert rt_list is not None
        assert list(r.filter(_FILTER_POOL)) == _union_filter(rt_list, _FILTER_POOL)

    @pytest.mark.parametrize("policy", [None, True, False])
    def test_disjoint_interval_union_filter_equivalent(
        self, policy: bool | None
    ) -> None:
        ss1 = SpecifierSet(">=1.0,<2.0", prereleases=policy)
        ss2 = SpecifierSet(">=3.0,<4.0", prereleases=policy)
        r = ss1.to_range() | ss2.to_range()
        rt_list = r.to_specifier_sets()
        assert rt_list is not None
        assert list(r.filter(_FILTER_POOL)) == _union_filter(rt_list, _FILTER_POOL)

    @pytest.mark.parametrize("policy", [None, True, False])
    def test_empty_range_carries_configured_policy(self, policy: bool | None) -> None:
        r = VersionRange.from_specifier_set(SpecifierSet(">=2,<1", prereleases=policy))
        sets = r.to_specifier_sets()
        assert sets is not None
        for s in sets:
            assert s._prereleases is policy


class TestFilterKeyAndAutodetect:
    """``VersionRange.filter(key=...)`` parity with ``SpecifierSet.filter``."""

    def test_key_yields_objects_not_versions(self) -> None:
        @dataclass(frozen=True)
        class Item:
            version: str
            payload: int

        items = [
            Item("0.5", 1),
            Item("1.0", 2),
            Item("1.5", 3),
            Item("2.0", 4),
        ]
        r = VersionRange.from_specifier_set(SpecifierSet(">=1.0,<2.0"))
        result = list(r.filter(items, key=lambda obj: obj.version))
        assert result == [Item("1.0", 2), Item("1.5", 3)]

    def test_key_multi_interval_autodetect_matches_specifier_set(self) -> None:
        # ``==1.* | ==3.*`` carries autodetected prereleases=None; the
        # PEP 440 buffering rule yields finals and drops pre-releases when
        # finals exist on each side. No single SpecifierSet expresses the
        # union, so the parity oracle is the per-piece filter union from
        # ``to_specifier_sets``.
        @dataclass(frozen=True)
        class Item:
            version: str
            payload: int

        items = [
            Item("0.5", 1),
            Item("1.0", 2),
            Item("1.0a1", 3),
            Item("1.5", 4),
            Item("3.0", 5),
            Item("3.0a1", 6),
        ]
        r = SpecifierSet("==1.*").to_range() | SpecifierSet("==3.*").to_range()
        from_range = list(r.filter(items, key=lambda obj: obj.version))
        sets = r.to_specifier_sets()
        assert sets is not None
        oracle: list[Item] = []
        for s in sets:
            for it in s.filter(items, key=lambda obj: obj.version):
                if it not in oracle:
                    oracle.append(it)
        assert (
            from_range
            == oracle
            == [
                Item("1.0", 2),
                Item("1.5", 4),
                Item("3.0", 5),
            ]
        )

    def test_key_singleton_set_filter_matches_round_trip(self) -> None:
        # ``>=1.0,<2.0`` has a single-set round trip, so the
        # ``SpecifierSet.filter`` oracle applies directly under ``key=``.
        @dataclass(frozen=True)
        class Item:
            version: str

        items = [Item("0.5"), Item("1.0a1"), Item("1.5"), Item("2.0a1")]
        ss = SpecifierSet(">=1.0,<2.0")
        r = ss.to_range()
        from_ss = list(ss.filter(items, key=lambda obj: obj.version))
        from_range = list(r.filter(items, key=lambda obj: obj.version))
        assert from_range == from_ss == [Item("1.5")]

    def test_key_buffering_holds_when_no_final_in_range(self) -> None:
        # When every in-range item is a pre-release, autodetect buffering
        # eventually yields them; ``key=`` must yield the wrapping objects.
        @dataclass(frozen=True)
        class Item:
            version: str

        # ``>=1.0a1,<2.0`` autodetects pre-releases from the RHS marker;
        # with no final in the pool, the buffered ``1.5a1`` is emitted.
        items = [Item("1.0a1"), Item("1.5a1")]
        ss = SpecifierSet(">=1.0a1,<2.0")
        r = ss.to_range()
        from_ss = list(ss.filter(items, key=lambda obj: obj.version))
        from_range = list(r.filter(items, key=lambda obj: obj.version))
        assert from_range == from_ss == [Item("1.0a1"), Item("1.5a1")]
