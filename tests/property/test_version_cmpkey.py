# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.

from __future__ import annotations

import itertools

import pytest
from hypothesis import given

from packaging._version_utils import version_cmpkey
from packaging.version import Version
from tests.property.strategies import SETTINGS, pep440_versions

pytestmark = pytest.mark.property


class TestVersionCmpkey:
    """``version_cmpkey`` must reproduce ``Version._key[:3]`` exactly and
    order versions the same way ``Version`` does."""

    @given(version=pep440_versions())
    @SETTINGS
    def test_matches_key_prefix(self, version: Version) -> None:
        """The key equals the leading three components of ``Version._key``."""
        assert version_cmpkey(version) == version._key[:3]

    @given(
        a=pep440_versions(include_local=False),
        b=pep440_versions(include_local=False),
    )
    @SETTINGS
    def test_ordering_agrees_with_version(self, a: Version, b: Version) -> None:
        """Ordering by the key agrees with ``Version`` ordering.

        Local segments are excluded: they live in the fourth key
        component, which ``version_cmpkey`` deliberately drops.
        """
        if a < b:
            assert version_cmpkey(a) < version_cmpkey(b)
        elif a > b:
            assert version_cmpkey(a) > version_cmpkey(b)
        else:
            assert version_cmpkey(a) == version_cmpkey(b)


# A fixed pool covering all-zero, trailing-zero, epoch, pre, post, dev forms.
_POOL = [
    Version(s)
    for s in (
        "0",
        "0.0",
        "0.0.0",
        "1",
        "1.0",
        "1.0.0",
        "1.2.3",
        "2!0",
        "2!0.0",
        "0.0.dev0",
        "0.0.post0",
        "1.0a1",
        "1.0b2",
        "1.0rc1",
        "1.0.post1",
        "1.0.dev1",
        "1.0.post1.dev2",
    )
]


@pytest.mark.parametrize("version", _POOL)
def test_pool_matches_key_prefix(version: Version) -> None:
    assert version_cmpkey(version) == version._key[:3]


def test_pool_ordering_is_pairwise_consistent() -> None:
    for a, b in itertools.combinations(_POOL, 2):
        if a < b:
            assert version_cmpkey(a) < version_cmpkey(b)
        elif a > b:
            assert version_cmpkey(a) > version_cmpkey(b)
        else:
            assert version_cmpkey(a) == version_cmpkey(b)
