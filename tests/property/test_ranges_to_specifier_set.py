# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.

"""Property tests for ``VersionRange.to_specifier_set`` round-tripping.

The conversion is partial (not every range is specifier-expressible).
When it succeeds, the round trip is structural under autodetect or
``prereleases=True`` and filter-equivalent under explicit
``prereleases=False`` (the encoder strips synthetic ``.dev0`` markers
that the clamp would mask anyway). ``None`` is allowed; silent semantic
drift is not.
"""

from __future__ import annotations

from functools import reduce
from typing import TYPE_CHECKING

import pytest
from hypothesis import given

from packaging.ranges import VersionRange
from packaging.specifiers import Specifier

from .strategies import (
    SETTINGS,
    eq_versions_only,
    pep440_specifier_strings,
    rich_specifier_sets,
    specifier_sets,
)

if TYPE_CHECKING:
    from packaging.specifiers import SpecifierSet

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


def _filter_equiv(a: VersionRange, b: VersionRange) -> bool:
    """Same versions accepted across the standard probe set."""
    return list(a.filter(_FILTER_PROBES)) == list(b.filter(_FILTER_PROBES))


def _equivalent_round_trip(source: VersionRange, recovered: VersionRange) -> bool:
    """Round-trip is structural under autodetect / True, filter-equivalent under False.

    Under explicit ``prereleases=False`` the encoder strips synthetic
    ``.dev0`` markers (see ``_strip_synthetic_dev0``), so the recovered
    range can differ structurally while admitting the same versions.
    """
    if source._prereleases_configured is False:
        return _filter_equiv(source, recovered)
    return source == recovered


@given(spec_set=specifier_sets(vary_prereleases=True))
@SETTINGS
def test_specifier_derived_ranges_always_have_a_specifier_set(
    spec_set: SpecifierSet,
) -> None:
    """Specifier-derived ranges always re-encode (incl. ``<0`` for empty)."""
    r = VersionRange.from_specifier_set(spec_set)
    converted = r.to_specifier_set()
    assert converted is not None, (
        f"specifier-derived range {r!r} should always re-encode "
        f"(input was {spec_set!r})"
    )
    assert _equivalent_round_trip(r, VersionRange.from_specifier_set(converted))


@given(spec_set=specifier_sets(vary_prereleases=True))
@SETTINGS
def test_to_specifier_sets_round_trips_when_not_none(
    spec_set: SpecifierSet,
) -> None:
    """If ``to_specifier_sets`` succeeds, its union is equivalent to ``r``."""
    r = VersionRange.from_specifier_set(spec_set)
    converted = r.to_specifier_sets()
    if converted is None:
        return
    assert converted, "to_specifier_sets must return a non-empty tuple"
    union = reduce(
        VersionRange.union,
        (VersionRange.from_specifier_set(s) for s in converted),
    )
    assert _equivalent_round_trip(r, union)


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
    ra = VersionRange.from_specifier_set(a)
    rb = VersionRange.from_specifier_set(b)
    inter = ra & rb
    converted = inter.to_specifier_set()
    assert converted is not None
    assert _equivalent_round_trip(inter, VersionRange.from_specifier_set(converted))


@given(a=specifier_sets(vary_prereleases=True), b=specifier_sets(vary_prereleases=True))
@SETTINGS
def test_to_specifier_sets_handles_union_when_intervals_are_specifier_shaped(
    a: SpecifierSet, b: SpecifierSet
) -> None:
    """Per-interval encoding succeeds for unions of specifier-derived ranges.

    Round-trips on the version subset: complement can flip
    ``_admit_arbitrary`` on a bounded range (PEP 440 has no operator that
    excludes only arbitrary strings), so structural equality on the flag
    would fail for unions touching such a complement.

    The drift guard on :meth:`to_specifier_sets` returns ``None`` when the
    recovered union would shift the autodetected pre-release policy;
    skip those draws.
    """
    if _conflicting_configured(a, b):
        return
    ra = VersionRange.from_specifier_set(a)
    rb = VersionRange.from_specifier_set(b)
    u = ra | rb
    converted = u.to_specifier_sets()
    if converted is None:
        return
    union = reduce(
        VersionRange.union,
        (VersionRange.from_specifier_set(s) for s in converted),
    )
    assert eq_versions_only(union, u) or _filter_equiv(union, u)


@given(spec_set=specifier_sets(vary_prereleases=True))
@SETTINGS
def test_to_specifier_set_implies_to_specifier_sets(
    spec_set: SpecifierSet,
) -> None:
    """``to_specifier_set is not None`` ⇒ ``to_specifier_sets is not None``."""
    r = VersionRange.from_specifier_set(spec_set)
    if r.to_specifier_set() is not None:
        assert r.to_specifier_sets() is not None


@given(spec_set=specifier_sets(vary_prereleases=True))
@SETTINGS
def test_complement_round_trips_or_returns_none(spec_set: SpecifierSet) -> None:
    """The complement of a specifier-derived range is often not
    specifier-expressible (e.g. ``~(>=1,<2)`` is two disjoint intervals).
    Exercises the partial-conversion contract: ``to_specifier_set`` either
    returns ``None`` or round-trips equivalently (structural under
    autodetect / True, filter-equivalent under explicit False)."""
    r = VersionRange.from_specifier_set(spec_set).complement()
    converted = r.to_specifier_set()
    if converted is not None:
        assert _equivalent_round_trip(r, VersionRange.from_specifier_set(converted))


@given(spec_string=pep440_specifier_strings(include_arbitrary=True))
@SETTINGS
def test_single_specifier_round_trips_when_encodable(spec_string: str) -> None:
    """Single-specifier ranges round-trip exactly when
    ``to_specifier_set`` returns a set.

    The narrow round-trip tests above lift through ``from_specifier_set``,
    which folds via ``intersect_ranges`` and silently canonicalizes the
    non-canonical leading interval some single specifiers (e.g. ``!=0.dev0``)
    produce. This property exercises the single-specifier entry point.
    Every single specifier has ``_admit_arbitrary=False``, and the
    encoder preserves it, so full equality holds.
    """
    r = Specifier(spec_string).to_range()
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
    round trip (the encoder collapses configured-None vs autodetect),
    so compare on the version subset.
    """
    ra, rb = a.to_range(), b.to_range()
    for r in (ra, ra & rb, ra | rb, ~ra):
        converted = r.to_specifier_set()
        if converted is not None:
            assert eq_versions_only(converted.to_range(), r)


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
    r = Specifier(spec_string).to_range()
    for variant in (r, ~r):
        converted = variant.to_specifier_set()
        if converted is None:
            continue
        assert list(variant.filter(_FILTER_PROBES)) == list(
            converted.filter(_FILTER_PROBES)
        )


@given(
    a=rich_specifier_sets(include_arbitrary=True),
    b=rich_specifier_sets(include_arbitrary=True),
)
@SETTINGS
def test_to_specifier_sets_round_trip_never_filter_drifts(
    a: SpecifierSet, b: SpecifierSet
) -> None:
    """Plural-form round-trip is filter-equivalent at every pre-release policy.

    Mirrors :func:`test_round_trip_never_filter_drifts` for the tuple API.
    When :meth:`to_specifier_sets` returns a tuple, feeding each piece back
    through :meth:`from_specifier_set` and unioning the results must filter
    identically to the source at ``prereleases`` in ``(None, True, False)``.
    """
    if a._prereleases != b._prereleases:
        return  # mismatched configured policies cannot combine
    ra, rb = a.to_range(), b.to_range()
    for variant in (ra, rb, ra & rb, ra | rb, ~ra, ~rb):
        sets = variant.to_specifier_sets()
        if sets is None:
            continue
        recovered = reduce(
            VersionRange.union,
            (VersionRange.from_specifier_set(piece) for piece in sets),
        )
        for policy in (None, True, False):
            assert list(recovered.filter(_FILTER_PROBES, prereleases=policy)) == list(
                variant.filter(_FILTER_PROBES, prereleases=policy)
            )
