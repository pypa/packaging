# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.

"""Property tests for ``VersionRange.to_specifier_set`` round-tripping.

The conversion is partial (not every range is specifier-expressible).
When it succeeds, the round trip is structurally equal to the source.
``None`` is allowed; silent semantic drift is not.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from hypothesis import example, given

from packaging.specifiers import SpecifierSet

from .strategies import (
    SETTINGS,
    VERSION_POOL,
    adjacency_exclusion_sets,
    pep440_specifier_strings,
    rich_specifier_sets,
    specifier_sets,
)

if TYPE_CHECKING:
    from packaging.ranges import VersionRange

pytestmark = pytest.mark.property


_FILTER_PROBES = [
    "0.5a1",
    "1.0",
    "1.0a1",
    "1.0.dev0",
    "1.0.post1",
    "1.5a1",
    "1.5",
    "2.0",
    "1!1.0",
    "0",
]


def _equivalent_round_trip(source: VersionRange, recovered: VersionRange) -> bool:
    """A successful round trip matches the same versions as the source.

    Whether the encoder keeps or drops the synthetic ``.dev0`` markers, the
    recovered set's range equals the source, so equality is exact, except that a
    range that is empty under its policy has no unique structural form (e.g.
    ``===0.dev0`` with ``prereleases=False`` recovers as the canonical ``<0``):
    any empty recovery is equivalent.
    """
    if source.is_empty and recovered.is_empty:
        return True
    return source == recovered


@given(spec_set=specifier_sets(vary_prereleases=True))
@SETTINGS
def test_specifier_derived_ranges_always_have_a_specifier_set(
    spec_set: SpecifierSet,
) -> None:
    """Specifier-derived ranges always re-encode (incl. ``<0`` for empty)."""
    r = spec_set.to_range()
    converted = r.to_specifier_set()
    assert converted is not None, (
        f"specifier-derived range {r!r} should always re-encode "
        f"(input was {spec_set!r})"
    )
    assert _equivalent_round_trip(r, converted.to_range())


@example(spec_set=SpecifierSet(">=3.8.dev0,<3.14", prereleases=True))
@example(spec_set=SpecifierSet(">3.8.post1"))
@example(spec_set=SpecifierSet("!=0.dev0"))
@example(spec_set=SpecifierSet("==1!0.*,<=1!0"))
@example(spec_set=SpecifierSet("!=1!0.dev0,==1!0.*"))
# Canonicalization folds these so two adjacent exclusions share one gap, a
# ``<pre.dev0`` upper becomes an inclusive AFTER_POSTS boundary, and the floor
# run collapses to one interval; each must still re-encode.
@example(spec_set=SpecifierSet("!=1.0,!=1.0.post0.dev0"))
@example(spec_set=SpecifierSet("!=1!0,!=1!0.post0.dev0", prereleases=True))
@example(spec_set=SpecifierSet("!=0.dev0,!=0.dev1"))
@example(spec_set=SpecifierSet("<1.0a1.dev0"))
# Adjacent exclusions can also collapse into the leading interval's lower; each
# recovers by anchoring at the dev family's prerelease-free base.
@example(spec_set=SpecifierSet(">=1.0,!=1.0,!=1.0.post0.dev0"))
@example(spec_set=SpecifierSet("==1.0.*,!=1.0.dev0,!=1.0.dev1"))
@example(spec_set=SpecifierSet("==1!0.*,!=1!0.dev0,!=1!0.dev1"))
@example(spec_set=SpecifierSet("!=2.*,!=3.dev0,!=3.dev1"))
@given(
    spec_set=rich_specifier_sets(include_arbitrary=True, vary_prereleases=True),
)
@SETTINGS
def test_rich_specifier_derived_ranges_always_have_a_specifier_set(
    spec_set: SpecifierSet,
) -> None:
    """The full version-bearing PEP 440 surface re-encodes too.

    The narrow :func:`specifier_sets` strategy only emits ``major.minor`` bounds,
    so it never produced the ``.dev0`` / post-release / wildcard / epoch /
    parseable ``===`` shapes whose recovery this exercises. Every version-bearing
    specifier-derived range has a single-set form, and the round trip is
    structurally exact. Arbitrary (non-version) ``===`` strings fall outside the
    contract and are covered separately by
    ``test_arbitrary_literal_true_policy_floor_none`` in tests/test_ranges.py.
    """
    r = spec_set.to_range()
    converted = r.to_specifier_set()
    assert converted is not None, (
        f"specifier-derived range {r!r} should always re-encode "
        f"(input was {spec_set!r})"
    )
    assert _equivalent_round_trip(r, converted.to_range())


@given(spec_set=adjacency_exclusion_sets())
@SETTINGS
def test_adjacency_collapse_ranges_always_re_encode(spec_set: SpecifierSet) -> None:
    """A version excluded with a run of its immediate successors merges into one
    gap; the specifier-derived range still re-encodes and round-trips.

    The independent strategies draw exclusions at random, so they essentially
    never produce a contiguous successor run. This exercises the ``!=`` chain,
    dev-run, wildcard-then-dev-run, and epoch floor-run recovery paths when the
    drawn lead and base line up.
    """
    r = spec_set.to_range()
    converted = r.to_specifier_set()
    assert converted is not None, (
        f"adjacency-collapse range {r!r} should always re-encode "
        f"(input was {spec_set!r})"
    )
    assert _equivalent_round_trip(r, converted.to_range())


# Omitted: test_to_specifier_sets_round_trips_when_not_none relied on the
# dropped plural ``VersionRange.to_specifier_sets``.


def _conflicting_configured(a: SpecifierSet, b: SpecifierSet) -> bool:
    """``VersionRange`` requires matching configured pre-release policies."""
    return a._prereleases != b._prereleases


@given(a=specifier_sets(vary_prereleases=True), b=specifier_sets(vary_prereleases=True))
@SETTINGS
def test_intersection_round_trips_when_not_none(
    a: SpecifierSet, b: SpecifierSet
) -> None:
    """SpecifierSet is closed under intersection."""
    if _conflicting_configured(a, b):
        return
    ra = a.to_range()
    rb = b.to_range()
    inter = ra & rb
    converted = inter.to_specifier_set()
    assert converted is not None
    assert _equivalent_round_trip(inter, converted.to_range())


# Omitted: test_to_specifier_sets_handles_union_when_intervals_are_specifier_shaped
# relied on the dropped plural ``VersionRange.to_specifier_sets``.


# Omitted: test_to_specifier_set_implies_to_specifier_sets relied on the dropped
# plural ``VersionRange.to_specifier_sets``.


@example(spec_set=SpecifierSet(">=2.3,<=2.7"))
@given(spec_set=specifier_sets(vary_prereleases=True))
@SETTINGS
def test_complement_round_trips_or_returns_none(spec_set: SpecifierSet) -> None:
    """The complement of a specifier-derived range is often not
    specifier-expressible (e.g. ``~(>=1,<2)`` is two disjoint intervals).
    Exercises the partial-conversion contract: ``to_specifier_set`` either
    returns ``None`` or round-trips equivalently (structural under
    autodetect / True, filter-equivalent under explicit False)."""
    r = spec_set.to_range().complement()
    converted = r.to_specifier_set()
    if converted is not None:
        assert _equivalent_round_trip(r, converted.to_range())


@given(spec_string=pep440_specifier_strings(include_arbitrary=True))
@SETTINGS
def test_single_specifier_round_trips_when_encodable(spec_string: str) -> None:
    """Single-specifier ranges round-trip exactly when
    ``to_specifier_set`` returns a set.

    The narrow round-trip tests above lift through ``to_range``, which folds
    via ``intersect_ranges`` and silently canonicalizes the non-canonical
    leading interval some single specifiers (e.g. ``!=0.dev0``) produce.
    This property exercises the single-specifier entry point. Every single
    specifier has ``_admit_arbitrary=False``, and the encoder preserves it,
    so full equality holds.
    """
    r = SpecifierSet(spec_string).to_range()
    converted = r.to_specifier_set()
    if converted is not None:
        assert converted.to_range() == r


@given(
    a=rich_specifier_sets(include_arbitrary=True),
    b=rich_specifier_sets(include_arbitrary=True),
)
@SETTINGS
def test_rich_algebra_round_trips_when_encodable(
    a: SpecifierSet, b: SpecifierSet
) -> None:
    """Ranges built by set algebra over the rich strategy round-trip on
    the version subset when ``to_specifier_set`` returns a set.

    The narrow round-trip strategy never reaches the encoder paths that
    handle ``!=V`` / ``!=V+local`` / ``!=V.*`` gaps, the ``==V+local``
    singleton, or multi-group unions; this property does. Pre-release
    policy tags can differ between the algebra result and its encoded
    round trip (the encoder collapses configured-None vs autodetect), and
    a ``MIN_VERSION`` lower bound canonicalizes to ``-inf``; both leave the
    accepted version set unchanged, so compare on the version subset.

    The complement variant ``~ra`` is split out into
    :func:`test_rich_algebra_complement_round_trips_when_encodable`.
    """
    ra, rb = a.to_range(), b.to_range()
    for r in (ra, ra & rb, ra | rb):
        converted = r.to_specifier_set()
        if converted is not None:
            recovered = converted.to_range()
            for v in VERSION_POOL:
                assert (v in recovered) == (v in r)


@example(spec_set=SpecifierSet(">=1.0,<=5.0"))
@given(spec_set=rich_specifier_sets(include_arbitrary=True))
@SETTINGS
def test_rich_algebra_complement_round_trips_when_encodable(
    spec_set: SpecifierSet,
) -> None:
    """``~r`` round-trips on the version subset when ``to_specifier_set``
    returns a set. Same contract as
    :func:`test_rich_algebra_round_trips_when_encodable` for the complement
    operand the original property covered in its ``~ra`` loop iteration."""
    r = spec_set.to_range().complement()
    converted = r.to_specifier_set()
    if converted is not None:
        recovered = converted.to_range()
        for v in VERSION_POOL:
            assert (v in recovered) == (v in r)


@given(spec_string=pep440_specifier_strings(include_arbitrary=True))
@SETTINGS
def test_round_trip_never_filter_drifts(spec_string: str) -> None:
    """When ``to_specifier_set`` returns a set, it filters identically.

    Guards the drift contract end-to-end: any time the encoder is willing
    to emit a single set, the recovered set must accept the same versions
    as the source range across a representative probe set. The drift_guard
    in ``to_specifier_set`` is what enforces this; the property is the
    observable contract.
    """
    r = SpecifierSet(spec_string).to_range()
    for variant in (r, ~r):
        converted = variant.to_specifier_set()
        if converted is None:
            continue
        assert list(variant.filter(_FILTER_PROBES)) == list(
            converted.filter(_FILTER_PROBES)
        )


# Omitted: test_to_specifier_sets_round_trip_never_filter_drifts relied on the
# dropped plural ``VersionRange.to_specifier_sets``.
