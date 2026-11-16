# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from packaging._ranges import matches_bounds_only
from packaging.specifiers import Specifier, SpecifierSet, _fast_match
from packaging.version import Version
from tests.property.strategies import (
    SETTINGS,
    nonlocal_versions,
    ops,
    pre_tags,
)

pytestmark = pytest.mark.property

tiny_ints = st.integers(min_value=0, max_value=2)


@st.composite
def same_release_versions(draw: st.DrawFn, base: Version) -> Version:
    """Generate a version that shares ``base``'s epoch and release.

    The pre, post, and dev segments vary, and trailing zeros may be added.
    """
    release = base.release + (0,) * draw(tiny_ints)
    pre = draw(st.none() | st.tuples(pre_tags, tiny_ints))
    post = draw(st.none() | tiny_ints)
    dev = draw(st.none() | tiny_ints)
    return Version.from_parts(
        epoch=base.epoch, release=release, pre=pre, post=post, dev=dev
    )


def _range_match(spec: Specifier, version: Version) -> bool:
    return matches_bounds_only(SpecifierSet([spec])._get_ranges(), version)


@given(
    op=ops,
    spec_version=nonlocal_versions(),
    candidate=nonlocal_versions(),
)
@SETTINGS
def test_fast_match_agrees_with_ranges(
    op: str, spec_version: Version, candidate: Version
) -> None:
    spec = Specifier(f"{op}{spec_version}")
    result = _fast_match(spec, candidate)
    if result is not None:
        assert result == _range_match(spec, candidate)


@given(op=ops, spec_version=nonlocal_versions(), data=st.data())
@SETTINGS
def test_fast_match_agrees_with_ranges_same_release(
    op: str, spec_version: Version, data: st.DataObject
) -> None:
    candidate = data.draw(same_release_versions(spec_version))
    spec = Specifier(f"{op}{spec_version}")
    result = _fast_match(spec, candidate)
    if result is not None:
        assert result == _range_match(spec, candidate)
