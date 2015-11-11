# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.
from __future__ import absolute_import, division, print_function

import string
import re

from ._parsing import stringStart, stringEnd, originalTextFor
from ._parsing import Literal as L, ZeroOrMore, Word, Optional, Regex
from .markers import MARKER_EXPR, Marker
from .specifiers import LegacySpecifier, Specifier, SpecifierSet


class InvalidRequirement(ValueError):
    """
    An invalid requirement was found, users should refer to PEP XXX.
    """


ALPHANUM = Word(string.ascii_letters + string.digits)

LBRACKET = L("[").suppress()
RBRACKET = L("]").suppress()
LPAREN = L("(").suppress()
RPAREN = L(")").suppress()
COMMA = L(",").suppress()
SEMICOLON = L(";").suppress()

IDENTIFIER_C = ALPHANUM + Word("-_.")
IDENTIFIER = ALPHANUM | (ALPHANUM + ZeroOrMore(IDENTIFIER_C) + ALPHANUM)

NAME = IDENTIFIER("name")
EXTRA = IDENTIFIER

EXTRAS = (LBRACKET + EXTRA + ZeroOrMore(COMMA + EXTRA) + RBRACKET)("extras")

VERSION_PEP440 = Regex(Specifier._regex_str, re.VERBOSE | re.IGNORECASE)
VERSION_LEGACY = Regex(LegacySpecifier._regex_str, re.VERBOSE | re.IGNORECASE)

VERSION_ONE = VERSION_PEP440 | VERSION_LEGACY
VERSION_MANY = VERSION_ONE + ZeroOrMore(COMMA + VERSION_ONE)
VERSION_SPEC = ((LPAREN + VERSION_MANY + RPAREN) | VERSION_MANY)

VERSION_SPEC = originalTextFor(VERSION_SPEC())("specifier")
VERSION_SPEC.setParseAction(
    lambda s, l, t: SpecifierSet(s[t._original_start:t._original_end])
)

MARKER_EXPR = originalTextFor(MARKER_EXPR())("marker")
MARKER_EXPR.setParseAction(
    lambda s, l, t: Marker(s[t._original_start:t._original_end])
)
MARKER = SEMICOLON + MARKER_EXPR

NAMED_REQUIREMENT = \
    NAME + Optional(EXTRAS) + Optional(VERSION_SPEC) + Optional(MARKER)

REQUIREMENT = stringStart + NAMED_REQUIREMENT + stringEnd


class Requirement(object):

    # TODO: Can we test whether something is contained within a requirement?
    #       If so how do we do that? Do we need to test against the _name_ of
    #       the thing as well as the version? What about the markers?
    # TODO: How do we handle the "extra" marker since it's special?
    # TODO: Can we normalize the name and extra name?

    def __init__(self, requirement_string):
        req = REQUIREMENT.parseString(requirement_string)

        self._name = req.name
        self._extras = req.extras.asList() if req.extras else None
        self._specifier = req.specifier if req.specifier else None
        self._marker = req.marker if req.marker else None

    def __str__(self):
        parts = [self._name]

        if self._extras:
            parts.append("[{0}]".format(",".join(sorted(self._extras))))

        if self._specifier:
            parts.append(str(self._specifier))

        if self._marker:
            parts.append("; {0}".format(self._marker))

        return "".join(parts)

    def __repr__(self):
        return "<Requirement({0!r})>".format(str(self))


if __name__ == "__main__":
    R = Requirement

    def t(r):
        print(repr(r))

    t(R("requests"))
    t(R("requests[security,other]"))
    t(R("requests[security,other]~=2.0"))
    t(R("requests>=2.0"))
    t(R("requests[security,other]; python_version < '2.7'"))
    t(R("requests[security,other] >=2.0 ; python_version < '2.7'"))
    t(R("requests[security,other] >=2.0,<6.0 ; python_version < '2.7'"))
    t(R("requests <10.0 ; python_version < '2.7'"))
