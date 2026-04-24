# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.

from __future__ import annotations

import sys

import pytest

from packaging.version import main


@pytest.mark.parametrize(
    ("args", "retcode"),
    [
        ("1.2 eq 1.2", 0),
        ("1.2 eq 1.2.0", 0),
        ("1.2 eq 1.2dev1", 1),
        ("1.2 == 1.2", 0),
        ("1.2 == 1.2.0", 0),
        ("1.2 == 1.2dev1", 1),
        ("1.2 ne 1.2.0", 1),
        ("1.2 ne 1.2dev1", 0),
        ("1.2 != 1.2.0", 1),
        ("1.2 != 1.2dev1", 0),
        ("1.2 lt 1.2.0", 1),
        ("1.2 lt 1.2dev1", 1),
        ("1.2 lt 1.3", 0),
        ("1.2 < 1.2.0", 1),
        ("1.2 < 1.2dev1", 1),
        ("1.2 < 1.3", 0),
        ("1.2 gt 1.2.0", 1),
        ("1.2 gt 1.2dev1", 0),
        ("1.2 gt 1.1", 0),
        ("1.2 > 1.2.0", 1),
        ("1.2 > 1.2dev1", 0),
        ("1.2 > 1.1", 0),
        ("1.2 le 1.2", 0),
        ("1.2 le 1.3", 0),
        ("1.2 le 1.1", 1),
        ("1.2 <= 1.2", 0),
        ("1.2 <= 1.3", 0),
        ("1.2 <= 1.1", 1),
        ("1.2 ge 1.2", 0),
        ("1.2 ge 1.1", 0),
        ("1.2 ge 1.3", 1),
        ("1.2 >= 1.2", 0),
        ("1.2 >= 1.1", 0),
        ("1.2 >= 1.3", 1),
        ("1.2 foo 1.2", 2),
        ("1.2 == unreal", 2),
    ],
)
def test_compare(monkeypatch: pytest.MonkeyPatch, args: str, retcode: int) -> None:
    monkeypatch.setattr(sys, "argv", ["prog", "compare", *args.split()])
    with pytest.raises(SystemExit) as excinfo:
        main()

    assert excinfo.value.code == retcode
