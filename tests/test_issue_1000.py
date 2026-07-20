"""Regression test for issue 1000: arbitrary equality parsing."""

import pytest

from packaging.specifiers import InvalidSpecifier, Specifier, SpecifierSet


def test_issue_1000():
    # Commas should not be part of an === version string.
    with pytest.raises(InvalidSpecifier):
        Specifier("===hello,")
    with pytest.raises(InvalidSpecifier):
        Specifier("===moo,<=0.1")
    # A comma between specifiers is a separator for SpecifierSet.
    s = SpecifierSet("===hello,<=0.1")
    assert len(s) == 2
    # We don't depend on order; just check that both are present.
    spec_strs = {str(spec) for spec in s}
    assert spec_strs == {"===hello", "<=0.1"}
    # Constructing from a list of Specifier objects should match.
    s2 = SpecifierSet([Specifier("===hello"), Specifier("<=0.1")])
    assert s == s2
    # A lone === without a comma must still work.
    lone = Specifier("===hello")
    assert lone.operator == "==="
    assert lone.version == "hello"
    # === with a version string that has no comma is fine.
    fine = Specifier("===<=0.1")
    assert fine.version == "<=0.1"
