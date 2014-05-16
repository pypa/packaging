# Copyright 2014 Donald Stufft
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from __future__ import absolute_import, division, print_function

import pytest

from packaging._structures import Infinity, NegativeInfinity


def test_infinity_repr():
    repr(Infinity) == "Infinity"


def test_negative_infinity_repr():
    repr(NegativeInfinity) == "-Infinity"


def test_infinity_hash():
    assert hash(Infinity) == hash(Infinity)


def test_negative_infinity_hash():
    assert hash(NegativeInfinity) == hash(NegativeInfinity)


@pytest.mark.parametrize("left", [1, "a", ("b", 4)])
def test_infinity_comparison(left):
    assert left < Infinity
    assert left <= Infinity
    assert not left == Infinity
    assert left != Infinity
    assert not left > Infinity
    assert not left >= Infinity


@pytest.mark.parametrize("left", [1, "a", ("b", 4)])
def test_negative_infinity_lesser(left):
    assert not left < NegativeInfinity
    assert not left <= NegativeInfinity
    assert not left == NegativeInfinity
    assert left != NegativeInfinity
    assert left > NegativeInfinity
    assert left >= NegativeInfinity


def test_infinty_equal():
    assert Infinity == Infinity


def test_negative_infinity_equal():
    assert NegativeInfinity == NegativeInfinity


def test_negate_infinity():
    assert isinstance(-Infinity, NegativeInfinity.__class__)


def test_negate_negative_infinity():
    assert isinstance(-NegativeInfinity, Infinity.__class__)
