# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.
from __future__ import annotations

import re

import pytest

from packaging._tokenizer import Tokenizer


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


def test_consume_unknown_token() -> None:
    tokenizer = Tokenizer("", rules={})
    with pytest.raises(AssertionError, match="Unknown token name: 'WS'"):
        tokenizer.consume("WS")


def test_enclosing_tokens_without_open_token() -> None:
    tokenizer = Tokenizer(
        "name", rules={"LP": re.compile(r"\("), "RP": re.compile(r"\)")}
    )
    with tokenizer.enclosing_tokens("LP", "RP", around="name"):
        pass
    assert tokenizer.position == 0


def test_consume_pending_token() -> None:
    tokenizer = Tokenizer(" ", rules={"WS": re.compile(" ")})
    assert tokenizer.check("WS")
    with pytest.raises(AssertionError, match="Cannot check for 'WS', already have"):
        tokenizer.consume("WS")
    assert tokenizer.read().text == " "
