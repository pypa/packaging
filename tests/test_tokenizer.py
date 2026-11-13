# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.
from __future__ import annotations

import re

import pytest

from packaging._parser import _parse_marker
from packaging._tokenizer import DEFAULT_RULES, Tokenizer


@pytest.mark.parametrize("whitespace", ["", " ", "\t", " \t  "])
def test_consume_preserves_next_token(whitespace: str) -> None:
    tokenizer = Tokenizer(
        f"{whitespace}name{whitespace}>=1",
        rules={
            "WS": re.compile(r"[ \t]+"),
            "NAME": re.compile(r"\w+"),
            "OP": re.compile(r">="),
        },
    )
    tokenizer.consume("WS")
    name = tokenizer.expect("NAME", expected="name")
    assert (name.text, name.position) == ("name", len(whitespace))
    tokenizer.consume("WS")
    operator = tokenizer.expect("OP", expected="operator")
    assert (operator.text, operator.position) == (">=", 4 + 2 * len(whitespace))


def test_consume_empty_match() -> None:
    tokenizer = Tokenizer("name", rules={"EMPTY": re.compile(r"")})
    tokenizer.consume("EMPTY")
    assert tokenizer.position == 0
    assert tokenizer.next_token is None


def test_match_pattern() -> None:
    tokenizer = Tokenizer("ab", rules={"B": re.compile("b")})
    assert tokenizer.match_pattern(re.compile("b")) is None
    assert tokenizer.position == 0
    match = tokenizer.match_pattern(re.compile("a"))
    assert match is not None
    assert tokenizer.position == 1
    assert tokenizer.expect("B", expected="b").position == 1


def test_enclosing_tokens() -> None:
    rules = {"LP": re.compile(r"\("), "RP": re.compile(r"\)")}
    tokenizer = Tokenizer("()", rules=rules)
    assert tokenizer.check("LP")
    with tokenizer.enclosing_tokens("LP", "RP", around="nothing"):
        assert tokenizer.position == 1
    assert tokenizer.position == 2


@pytest.mark.parametrize("op", ["==", "in", "not in"])
def test_marker_item_with_other_rules(op: str) -> None:
    # Rules other than the default mapping must use the token path.
    tokenizer = Tokenizer(f'os_name {op} "a"', rules=dict(DEFAULT_RULES))
    assert str(_parse_marker(tokenizer)) == (
        f"[(<Variable('os_name')>, <Op({op!r})>, <Value('a')>)]"
    )


@pytest.mark.parametrize(
    "source",
    [
        '  os_name == "posix"',
        'os_name == "posix"  ',
        '(  os_name == "posix")',
        '(os_name == "posix"  )',
    ],
)
def test_marker_with_partial_whitespace_rule(source: str) -> None:
    rules = dict(DEFAULT_RULES, WS=re.compile(r"[ \t]"))
    tokenizer = Tokenizer(source, rules=rules)
    marker = _parse_marker(tokenizer)

    assert tokenizer.position == len(source)
    if isinstance(marker[0], list):
        marker = marker[0]
    atom = marker[0]
    assert isinstance(atom, tuple)
    assert tuple(node.value for node in atom) == ("os_name", "==", "posix")
