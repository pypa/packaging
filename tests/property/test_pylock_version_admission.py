# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.

"""Reject unsupported lock-format major versions regardless of release stage."""

from __future__ import annotations

import pytest
from hypothesis import example, given
from hypothesis import strategies as st

from packaging.pylock import Pylock, PylockUnsupportedVersionError

from .strategies import SETTINGS

pytestmark = pytest.mark.property


@given(
    major=st.integers(min_value=2, max_value=5),
    minor=st.integers(min_value=0, max_value=20),
    suffix=st.sampled_from([".dev0", ".dev1", "a0", "b1", "rc1", "", ".post1"]),
)
@example(major=2, minor=0, suffix=".dev0")
@example(major=2, minor=0, suffix="rc1")
@SETTINGS
def test_unsupported_major_versions_are_rejected(
    major: int, minor: int, suffix: str
) -> None:
    data = {
        "lock-version": f"{major}.{minor}{suffix}",
        "created-by": "test",
        "packages": [],
    }
    with pytest.raises(PylockUnsupportedVersionError):
        Pylock.from_dict(data)
