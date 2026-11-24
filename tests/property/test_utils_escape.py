# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from packaging.utils import canonicalize_name, escape_name

pytestmark = pytest.mark.property


@given(st.text())
def test_escape_name_matches_canonicalize_name(name: str) -> None:
    assert escape_name(name) == canonicalize_name(name).replace("-", "_")
