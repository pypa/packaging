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

import itertools
import re

from ._compat import string_types
from .version import Version, LegacyVersion, parse


class InvalidSpecifier(ValueError):
    """
    An invalid specifier was found, users should refer to PEP 440.
    """


class Specifier(object):

    _regex = re.compile(
        r"""
        ^
        \s*
        (?P<operator>(~=|==|!=|<=|>=|<|>|===))
        (?P<version>
            (?:
                # The identity operators allow for an escape hatch that will
                # do an exact string match of the version you wish to install.
                # This will not be parsed by PEP 440 and we cannot determine
                # any semantic meaning from it. This operator is discouraged
                # but included entirely as an escape hatch.
                (?<====)  # Only match for the identity operator
                \s*
                [^\s]*    # We just match everything, except for whitespace
                          # since we are only testing for strict identity.
            )
            |
            (?:
                # The (non)equality operators allow for wild card and local
                # versions to be specified so we have to define these two
                # operators separately to enable that.
                (?<===|!=)            # Only match for equals and not equals

                \s*
                v?
                (?:[0-9]+!)?          # epoch
                [0-9]+(?:\.[0-9]+)*   # release
                (?:                   # pre release
                    [-_\.]?
                    (a|b|c|rc|alpha|beta|pre|preview)
                    [-_\.]?
                    [0-9]*
                )?
                (?:                   # post release
                    (?:-[0-9]+)|(?:[-_\.]?(post|rev|r)[-_\.]?[0-9]*)
                )?

                # You cannot use a wild card and a dev or local version
                # together so group them with a | and make them optional.
                (?:
                    (?:[-_\.]?dev[-_\.]?[0-9]*)?         # dev release
                    (?:\+[a-z0-9]+(?:[-_\.][a-z0-9]+)*)? # local
                    |
                    \.\*  # Wild card syntax of .*
                )?
            )
            |
            (?:
                # The compatible operator requires at least two digits in the
                # release segment.
                (?<=~=)               # Only match for the compatible operator

                \s*
                v?
                (?:[0-9]+!)?          # epoch
                [0-9]+(?:\.[0-9]+)+   # release  (We have a + instead of a *)
                (?:                   # pre release
                    [-_\.]?
                    (a|b|c|rc|alpha|beta|pre|preview)
                    [-_\.]?
                    [0-9]*
                )?
                (?:                                   # post release
                    (?:-[0-9]+)|(?:[-_\.]?(post|rev|r)[-_\.]?[0-9]*)
                )?
                (?:[-_\.]?dev[-_\.]?[0-9]*)?          # dev release
            )
            |
            (?:
                # All other operators only allow a sub set of what the
                # (non)equality operators do. Specifically they do not allow
                # local versions to be specified nor do they allow the prefix
                # matching wild cards.
                (?<!==|!=|~=)         # We have special cases for these
                                      # operators so we want to make sure they
                                      # don't match here.

                \s*
                v?
                (?:[0-9]+!)?          # epoch
                [0-9]+(?:\.[0-9]+)*   # release
                (?:                   # pre release
                    [-_\.]?
                    (a|b|c|rc|alpha|beta|pre|preview)
                    [-_\.]?
                    [0-9]*
                )?
                (?:                                   # post release
                    (?:-[0-9]+)|(?:[-_\.]?(post|rev|r)[-_\.]?[0-9]*)
                )?
                (?:[-_\.]?dev[-_\.]?[0-9]*)?          # dev release
            )
        )
        \s*
        $
        """,
        re.VERBOSE | re.IGNORECASE,
    )

    _operators = {
        "~=": "compatible",
        "==": "equal",
        "!=": "not_equal",
        "<=": "less_than_equal",
        ">=": "greater_than_equal",
        "<": "less_than",
        ">": "greater_than",
        "===": "arbitrary",
    }

    def __init__(self, specs="", prereleases=None):
        # Split on comma to get each individual specification
        _specs = set()
        for spec in (s for s in specs.split(",") if s):
            match = self._regex.search(spec)
            if not match:
                raise InvalidSpecifier("Invalid specifier: '{0}'".format(spec))

            _specs.add(
                (
                    match.group("operator").strip(),
                    match.group("version").strip(),
                )
            )

        # Set a frozen set for our specifications
        self._specs = frozenset(_specs)

        # Store whether or not this Specifier should accept prereleases
        self._prereleases = prereleases

    def __repr__(self):
        return "<Specifier({0})>".format(repr(str(self)))

    def __str__(self):
        return ",".join(["".join(s) for s in sorted(self._specs)])

    def __hash__(self):
        return hash(self._specs)

    def __and__(self, other):
        if isinstance(other, string_types):
            other = Specifier(other)
        elif not isinstance(other, Specifier):
            return NotImplemented

        return self.__class__(",".join([str(self), str(other)]))

    def __eq__(self, other):
        if isinstance(other, string_types):
            other = Specifier(other)
        elif not isinstance(other, Specifier):
            return NotImplemented

        return self._specs == other._specs

    def __ne__(self, other):
        if isinstance(other, string_types):
            other = Specifier(other)
        elif not isinstance(other, Specifier):
            return NotImplemented

        return self._specs != other._specs

    def _get_operator(self, op):
        return getattr(self, "_compare_{0}".format(self._operators[op]))

    def _compare_compatible(self, prospective, spec):
        # Compatible releases have an equivalent combination of >= and ==. That
        # is that ~=2.2 is equivalent to >=2.2,==2.*. This allows us to
        # implement this in terms of the other specifiers instead of
        # implementing it ourselves. The only thing we need to do is construct
        # the other specifiers.

        # We want everything but the last item in the version, but we want to
        # ignore post and dev releases and we want to treat the pre-release as
        # it's own separate segment.
        prefix = ".".join(
            list(
                itertools.takewhile(
                    lambda x: (not x.startswith("post")
                               and not x.startswith("dev")),
                    _version_split(spec),
                )
            )[:-1]
        )

        # Add the prefix notation to the end of our string
        prefix += ".*"

        return (self._get_operator(">=")(prospective, spec)
                and self._get_operator("==")(prospective, prefix))

    def _compare_equal(self, prospective, spec):
        # We need special logic to handle prefix matching
        if spec.endswith(".*"):
            # Split the spec out by dots, and pretend that there is an implicit
            # dot in between a release segment and a pre-release segment.
            spec = _version_split(spec[:-2])  # Remove the trailing .*

            # Split the prospective version out by dots, and pretend that there
            # is an implicit dot in between a release segment and a pre-release
            # segment.
            prospective = _version_split(str(prospective))

            # Shorten the prospective version to be the same length as the spec
            # so that we can determine if the specifier is a prefix of the
            # prospective version or not.
            prospective = prospective[:len(spec)]

            # Pad out our two sides with zeros so that they both equal the same
            # length.
            spec, prospective = _pad_version(spec, prospective)
        else:
            # Convert our spec string into a Version
            spec = Version(spec)

            # If the specifier does not have a local segment, then we want to
            # act as if the prospective version also does not have a local
            # segment.
            if not spec.local:
                prospective = Version(prospective.public)

        return prospective == spec

    def _compare_not_equal(self, prospective, spec):
        return not self._compare_equal(prospective, spec)

    def _compare_less_than_equal(self, prospective, spec):
        return prospective <= Version(spec)

    def _compare_greater_than_equal(self, prospective, spec):
        return prospective >= Version(spec)

    def _compare_less_than(self, prospective, spec):
        # Less than are defined as exclusive operators, this implies that
        # pre-releases do not match for the same series as the spec. This is
        # implemented by making <V imply !=V.*.
        return (prospective < Version(spec)
                and self._get_operator("!=")(prospective, spec + ".*"))

    def _compare_greater_than(self, prospective, spec):
        # Greater than are defined as exclusive operators, this implies that
        # pre-releases do not match for the same series as the spec. This is
        # implemented by making >V imply !=V.*.
        return (prospective > Version(spec)
                and self._get_operator("!=")(prospective, spec + ".*"))

    def _compare_arbitrary(self, prospective, spec):
        return str(prospective).lower() == str(spec).lower()

    @property
    def prereleases(self):
        # If there is an explicit prereleases set for this, then we'll just
        # blindly use that.
        if self._prereleases is not None:
            return self._prereleases

        # Look at all of our specifiers and determine if they are inclusive
        # operators, and if they are if they are including an explicit
        # prerelease.
        for spec, version in self._specs:
            if spec in ["==", ">=", "<=", "~="]:
                # The == specifier can include a trailing .*, if it does we
                # want to remove before parsing.
                if spec == "==" and version.endswith(".*"):
                    version = version[:-2]

                # Parse the version, and if it is a pre-release than this
                # specifier allows pre-releases.
                if parse(version).is_prerelease:
                    return True

        return False

    @prereleases.setter
    def prereleases(self, value):
        self._prereleases = value

    def contains(self, item, prereleases=None):
        # Determine if prereleases are to be allowed or not.
        if prereleases is None:
            prereleases = self.prereleases

        # Normalize item to a Version or LegacyVersion, this allows us to have
        # a shortcut for ``"2.0" in Specifier(">=2")
        if isinstance(item, (Version, LegacyVersion)):
            version_item = item
        else:
            try:
                version_item = Version(item)
            except ValueError:
                version_item = LegacyVersion(item)

        # Determine if we should be supporting prereleases in this specifier
        # or not, if we do not support prereleases than we can short circuit
        # logic if this version is a prereleases.
        if version_item.is_prerelease and not prereleases:
            return False

        # Detect if we have any specifiers, if we do not then anything matches
        # and we can short circuit all this logic.
        if not self._specs:
            return True

        # If we're operating on a LegacyVersion, then we can only support
        # arbitrary comparison so do a quick check to see if the spec contains
        # any non arbitrary specifiers
        if isinstance(version_item, LegacyVersion):
            if any(op != "===" for op, _ in self._specs):
                return False

        # Ensure that the passed in version matches all of our version
        # specifiers
        return all(
            self._get_operator(op)(
                version_item if op != "===" else item,
                spec,
            )
            for op, spec, in self._specs
        )

    def filter(self, iterable, prereleases=None):
        iterable = list(iterable)
        yielded = False
        found_prereleases = []

        kw = {"prereleases": prereleases if prereleases is not None else True}

        # Attempt to iterate over all the values in the iterable and if any of
        # them match, yield them.
        for version in iterable:
            if not isinstance(version, (Version, LegacyVersion)):
                parsed_version = parse(version)
            else:
                parsed_version = version

            if self.contains(parsed_version, **kw):
                # If our version is a prerelease, and we were not set to allow
                # prereleases, then we'll store it for later incase nothing
                # else matches this specifier.
                if (parsed_version.is_prerelease
                        and not (prereleases or self.prereleases)):
                    found_prereleases.append(version)
                # Either this is not a prerelease, or we should have been
                # accepting prereleases from the begining.
                else:
                    yielded = True
                    yield version

        # Now that we've iterated over everything, determine if we've yielded
        # any values, and if we have not and we have any prereleases stored up
        # then we will go ahead and yield the prereleases.
        if not yielded and found_prereleases:
            for version in found_prereleases:
                yield version


_prefix_regex = re.compile(r"^([0-9]+)((?:a|b|c|rc)[0-9]+)$")


def _version_split(version):
    result = []
    for item in version.split("."):
        match = _prefix_regex.search(item)
        if match:
            result.extend(match.groups())
        else:
            result.append(item)
    return result


def _pad_version(left, right):
    left_split, right_split = [], []

    # Get the release segment of our versions
    left_split.append(list(itertools.takewhile(lambda x: x.isdigit(), left)))
    right_split.append(list(itertools.takewhile(lambda x: x.isdigit(), right)))

    # Get the rest of our versions
    left_split.append(left[len(left_split):])
    right_split.append(left[len(right_split):])

    # Insert our padding
    left_split.insert(
        1,
        ["0"] * max(0, len(right_split[0]) - len(left_split[0])),
    )
    right_split.insert(
        1,
        ["0"] * max(0, len(left_split[0]) - len(right_split[0])),
    )

    return (
        list(itertools.chain(*left_split)),
        list(itertools.chain(*right_split)),
    )
