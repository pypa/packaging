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

import collections
import itertools
import re

from ._compat import string_types
from ._structures import Infinity


__all__ = ["Version", "Specifier"]


_Version = collections.namedtuple(
    "_Version",
    ["epoch", "release", "dev", "pre", "post", "local"],
)


class InvalidVersion(ValueError):
    """
    An invalid version was found, users should refer to PEP 440.
    """


class Version(object):

    _regex = re.compile(
        r"""
        ^
        (?:
            (?:(?P<epoch>[0-9]+):)?               # epoch
            (?P<release>[0-9]+(?:\.[0-9]+)*)      # release segment
            (?P<pre>                              # pre release
                [-\.]?
                (?P<pre_l>(a|b|c|rc|alpha|beta))  #  - pre-release letter
                (?P<pre_n>[0-9]+)?                #  - pre-release number
            )?
            (?P<post>                             # post release
                [-\.]?
                (?P<post_l>post)
                (?P<post_n>[0-9]+)?
            )?
            (?P<dev>                              # dev release
                [-\.]?
                (?P<dev_l>dev)
                (?P<dev_n>[0-9]+)?
            )?
        )
        (?:\+(?P<local>[a-z0-9]+(?:[a-z0-9\.]*[a-z0-9])?))? # local version
        $
        """,
        re.VERBOSE | re.IGNORECASE,
    )

    def __init__(self, version):
        # Validate the version and parse it into pieces
        match = self._regex.search(version)
        if not match:
            raise InvalidVersion("Invalid version: '{0}'".format(version))

        # Store the parsed out pieces of the version
        self._version = _Version(
            epoch=int(match.group("epoch")) if match.group("epoch") else 0,
            release=_parse_release_version(match.group("release")),
            pre=_parse_letter_version(
                match.group("pre_l"),
                match.group("pre_n"),
            ),
            post=_parse_letter_version(
                match.group("post_l"),
                match.group("post_n"),
            ),
            dev=_parse_letter_version(
                match.group("dev_l"),
                match.group("dev_n"),
            ),
            local=_parse_local_version(match.group("local")),
        )

        # Generate a key which will be used for sorting
        self._key = _cmpkey(
            self._version.epoch,
            self._version.release,
            self._version.pre,
            self._version.post,
            self._version.dev,
            self._version.local,
        )

    def __repr__(self):
        return "<Version({0})>".format(repr(str(self)))

    def __str__(self):
        parts = []

        # Epoch
        if self._version.epoch != 0:
            parts.append("{0}:".format(self._version.epoch))

        # Release segment
        parts.append(".".join(str(x) for x in self._version.release))

        # Pre-release
        if self._version.pre is not None:
            parts.append("".join(str(x) for x in self._version.pre))

        # Post-release
        if self._version.post is not None:
            parts.append(".post{0}".format(self._version.post[1]))

        # Development release
        if self._version.dev is not None:
            parts.append(".dev{0}".format(self._version.dev[1]))

        # Local version segment
        if self._version.local is not None:
            parts.append(
                "+{0}".format(".".join(str(x) for x in self._version.local))
            )

        return "".join(parts)

    def __hash__(self):
        return hash(self._key)

    def __lt__(self, other):
        return self._compare(other, lambda s, o: s < o)

    def __le__(self, other):
        return self._compare(other, lambda s, o: s <= o)

    def __eq__(self, other):
        return self._compare(other, lambda s, o: s == o)

    def __ge__(self, other):
        return self._compare(other, lambda s, o: s >= o)

    def __gt__(self, other):
        return self._compare(other, lambda s, o: s > o)

    def __ne__(self, other):
        return self._compare(other, lambda s, o: s != o)

    def _compare(self, other, method):
        if not isinstance(other, Version):
            return NotImplemented

        return method(self._key, other._key)

    @property
    def public(self):
        return str(self).split("+", 1)[0]

    @property
    def local(self):
        version_string = str(self)
        if "+" in version_string:
            return version_string.split("+", 1)[1]

    @property
    def is_prerelease(self):
        return bool(self._version.dev or self._version.pre)


def _parse_release_version(part):
    """
    Takes a string like "1.0.4.0" and turns it into (1, 0, 4).
    """
    return tuple(
        reversed(
            list(
                itertools.dropwhile(
                    lambda x: x == 0,
                    reversed(list(int(i) for i in part.split("."))),
                )
            )
        )
    )


def _parse_letter_version(letter, number):
    if letter:
        # We consider there to be an implicit 0 in a pre-release if there is
        # not a numeral associated with it.
        if number is None:
            number = 0

        # We consider the "rc" form of a pre-release to be long-form for the
        # "c" form, thus we normalize "rc" to "c" so we can properly compare
        # them as equal.
        if letter == "rc":
            letter = "c"

        return letter, int(number)


def _parse_local_version(local):
    """
    Takes a string like abc.1.twelve and turns it into ("abc", 1, "twelve").
    """
    if local is not None:
        return tuple(
            part if not part.isdigit() else int(part)
            for part in local.split(".")
        )


def _cmpkey(epoch, release, pre, post, dev, local):
    # We need to "trick" the sorting algorithm to put 1.0.dev0 before 1.0a0.
    # We'll do this by abusing the pre segment, but we _only_ want to do this
    # if there is not a pre or a post segment. If we have one of those then
    # the normal sorting rules will handle this case correctly.
    if pre is None and post is None and dev is not None:
        pre = -Infinity
    # Versions without a pre-release (except as noted above) should sort after
    # those with one.
    elif pre is None:
        pre = Infinity

    # Versions without a post segment should sort before those with one.
    if post is None:
        post = -Infinity

    # Versions without a development segment should sort after those with one.
    if dev is None:
        dev = Infinity

    if local is None:
        # Versions without a local segment should sort before those with one.
        local = -Infinity
    else:
        # Versions with a local segment need that segment parsed to implement
        # the sorting rules in PEP440.
        # - Alpha numeric segments sort before numeric segments
        # - Alpha numeric segments sort lexicographically
        # - Numeric segments sort numerically
        # - Shorter versions sort before longer versions when the prefixes
        #   match exactly
        local = tuple(
            (i, "") if isinstance(i, int) else (-Infinity, i)
            for i in local
        )

    return epoch, release, pre, post, dev, local


class InvalidSpecifier(ValueError):
    """
    An invalid specifier was found, users should refer to PEP 440.
    """


class Specifier(object):

    _regex = re.compile(
        r"""
        ^
        (?P<operator>(~=|==|!=|<=|>=|<|>|===))
        (?P<version>
            (?:
                # The identity operators allow for an escape hatch that will
                # do an exact string match of the version you wish to install.
                # This will not be parsed by PEP 440 and we cannot determine
                # any semantic meaning from it. This operator is discouraged
                # but included entirely as an escape hatch.
                (?<====)  # Only match for the identity operator
                .*        # We just match everything, since we are only testing
                          # for strict identity.
            )
            |
            (?:
                # The (non)equality operators allow for wild card and local
                # versions to be specified so we have to define these two
                # operators separately to enable that.
                (?<===|!=)            # Only match for equals and not equals

                (?:[0-9]+:)?          # epoch
                [0-9]+(?:\.[0-9]+)*   # release
                (?:[-\.]?(a|b|c|rc|alpha|beta)[0-9]*)? # pre release
                (?:[-\.]?post[0-9]*)? # post release

                # You cannot use a wild card and a dev or local version
                # together so group them with a | and make them optional.
                (?:
                    (?:[-\.]?dev[0-9]*)?                       # dev release
                    (?:\+[a-z0-9]+(?:[a-z0-9_\.+]*[a-z0-9])?)? # local
                    |
                    \.\*  # Wild card syntax of .*
                )?
            )
            |
            (?:
                # The compatible operator requires at least two digits in the
                # release segment.
                (?<=~=)               # Only match for the compatible operator

                (?:[0-9]+:)?          # epoch
                [0-9]+(?:\.[0-9]+)+   # release  (We have a + instead of a *)
                (?:[-\.]?(a|b|c|rc|alpha|beta)[0-9]*)? # pre release
                (?:[-\.]?post[0-9]*)? # post release
                (?:[-\.]?dev[0-9]*)?  # dev release
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

                (?:[0-9]+:)?          # epoch
                [0-9]+(?:\.[0-9]+)*   # release
                (?:[-\.]?(a|b|c|rc|alpha|beta)[0-9]*)? # pre release
                (?:[-\.]?post[0-9]*)? # post release
                (?:[-\.]?dev[0-9]*)?  # dev release
            )
        )
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
        "===": "identity",
    }

    def __init__(self, specs, prereleases=False):
        # Normalize the specification to remove all of the whitespace
        specs = specs.replace(" ", "")

        # Split on comma to get each individual specification
        _specs = set()
        for spec in specs.split(","):
            match = self._regex.search(spec)
            if not match:
                raise InvalidSpecifier("Invalid specifier: '{0}'".format(spec))

            _specs.add(
                (match.group("operator"), match.group("version"))
            )

        # Set a frozen set for our specifications
        self._specs = frozenset(_specs)

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

    def __contains__(self, item):
        # Normalize item to a Version, this allows us to have a shortcut for
        # ``"2.0" in Specifier(">=2")
        version_item = item
        if not isinstance(item, Version):
            try:
                version_item = Version(item)
            except ValueError:
                # If we cannot parse this as a version, then we can only
                # support identity comparison so do a quick check to see if the
                # spec contains any non identity specifiers
                #
                # This will return False if we do not have any specifiers, this
                # is on purpose as a non PEP 440 version should require
                # explicit opt in because otherwise they cannot be sanely
                # prioritized
                if (not self._specs
                        or any(op != "===" for op, _ in self._specs)):
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

    def _compare_identity(self, prospective, spec):
        return prospective.lower() == spec.lower()


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
