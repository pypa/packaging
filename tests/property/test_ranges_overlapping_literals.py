# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.

"""Check named prerelease admission with related strings and parsed versions."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from packaging.specifiers import SpecifierSet
from packaging.version import Version

from .strategies import SETTINGS, LiteralCase, literal_cases

pytestmark = pytest.mark.property


def expected_filter(case: LiteralCase, policy: bool | None) -> list[str | Version]:
    """Partition by position so equal versions retain their distinct input text."""
    values = case.versions
    finals = {
        i for i, value in enumerate(values) if not Version(str(value)).is_prerelease
    }
    named = {
        i
        for i, value in enumerate(values)
        if str(value).lower() == case.literal.lower()
    }
    if policy is True:
        order = list(range(len(values)))
    elif policy is False:
        order = sorted(finals)
    elif finals:
        order = sorted(finals | named)
    else:
        order = sorted(named) + [i for i in range(len(values)) if i not in named]
    return [values[i] for i in order]


@given(
    case=literal_cases(vary_prereleases=True),
    override=st.sampled_from([None, False, True]),
)
@SETTINGS
def test_named_literal_admission_survives_composition(
    case: LiteralCase, override: bool | None
) -> None:
    bounds = case.bounds.to_range()
    policy = case.bounds.prereleases
    named = SpecifierSet(f"==={case.literal}", prereleases=policy).to_range()
    major = Version(case.literal).release[0]
    lower = SpecifierSet(f">={major}.4", prereleases=policy).to_range()
    upper = SpecifierSet(f">={major}.7", prereleases=policy).to_range()
    expected = expected_filter(case, policy if override is None else override)
    for combined in (bounds | named, named | bounds):
        for result in (combined, combined & lower, combined - upper):
            assert list(result.filter(case.versions, prereleases=override)) == expected
            items = [{"version": value} for value in case.versions]
            assert [
                item["version"]
                for item in result.filter(
                    items, key=lambda item: item["version"], prereleases=override
                )
            ] == expected


@given(
    case=literal_cases(vary_prereleases=True),
    override=st.sampled_from([None, False, True]),
)
@SETTINGS
def test_exclusion_and_restoration_preserve_admission(
    case: LiteralCase, override: bool | None
) -> None:
    bounds = case.bounds.to_range()
    named = SpecifierSet(
        f"==={case.literal}", prereleases=case.bounds.prereleases
    ).to_range()
    excluded = bounds - named
    expected = list(bounds.filter(case.versions, prereleases=override))
    for restored in (excluded | bounds, bounds | excluded):
        assert list(restored.filter(case.versions, prereleases=override)) == expected

    removed = (bounds | named) - named
    assert list(removed.filter(case.versions, prereleases=override)) == list(
        excluded.filter(case.versions, prereleases=override)
    )
