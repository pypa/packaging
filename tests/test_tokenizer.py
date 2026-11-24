# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.
from __future__ import annotations

import re

import pytest

from packaging._parser import _parse_full_marker, _parse_requirement
from packaging._tokenizer import Tokenizer


@pytest.mark.parametrize("whitespace", ["", " ", "\t", " \t  "])
def test_consume_preserves_next_token(whitespace: str) -> None:
    tokenizer = Tokenizer(f"{whitespace}name{whitespace}>=1")
    tokenizer.consume("WS")
    name = tokenizer.expect("IDENTIFIER", expected="name")
    assert (name.text, name.position) == ("name", len(whitespace))
    tokenizer.consume("WS")
    operator = tokenizer.expect("OP", expected="operator")
    assert (operator.text, operator.position) == (">=", 4 + 2 * len(whitespace))


def test_consume_empty_match() -> None:
    tokenizer = Tokenizer("")
    tokenizer.consume("END")
    assert tokenizer.position == 0
    assert tokenizer.next_token is None


def test_match_pattern() -> None:
    tokenizer = Tokenizer("a>=1")
    assert tokenizer.match_pattern(re.compile("b")) is None
    assert tokenizer.position == 0
    match = tokenizer.match_pattern(re.compile("a"))
    assert match is not None
    assert tokenizer.position == 1
    assert tokenizer.expect("OP", expected="operator").position == 1


def test_enclosing_tokens() -> None:
    tokenizer = Tokenizer("()")
    assert tokenizer.check("LEFT_PARENTHESIS")
    with tokenizer.enclosing_tokens(
        "LEFT_PARENTHESIS", "RIGHT_PARENTHESIS", around="nothing"
    ):
        assert tokenizer.position == 1
    assert tokenizer.position == 2


@pytest.mark.parametrize(
    "source",
    [
        '  os_name == "posix"',
        'os_name == "posix"  ',
        '(  os_name == "posix")',
        '(os_name == "posix"  )',
    ],
)
def test_marker_with_whitespace(source: str) -> None:
    tokenizer = Tokenizer(source)
    marker = _parse_full_marker(tokenizer)

    assert tokenizer.position == len(source)
    if isinstance(marker[0], list):
        marker = marker[0]
    atom = marker[0]
    assert isinstance(atom, tuple)
    assert tuple(node.value for node in atom) == ("os_name", "==", "posix")


@pytest.mark.parametrize(
    ("source", "specifier"),
    [
        ("name   >=1.0", ">=1.0"),
        ("name[a]  >=1.0", ">=1.0"),
        ("name ( >=1.0 ) ", ">=1.0"),
        ("name     ; os_name == 'posix'", ""),
        ("name >=1.0 ; os_name == 'posix'  ", ">=1.0"),
    ],
)
def test_requirement_with_whitespace(source: str, specifier: str) -> None:
    tokenizer = Tokenizer(source)
    parsed = _parse_requirement(tokenizer)

    assert tokenizer.position == len(source)
    assert parsed.name == "name"
    assert str(parsed.specifier).strip() == specifier
