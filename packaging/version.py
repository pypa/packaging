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

from ._structures import Infinity

# TODO: We deviate from the spec in that we have no implicit specifier operator
#       instead we mandate all specifiers must include an explicit operator.

__all__ = ["Version"]


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
            (?:(?P<epoch>[0-9]+):)?          # epoch
            (?P<release>[0-9]+(?:\.[0-9]+)*) # release segment
            (?P<pre>                         # pre release
                (?P<pre_l>(a|b|c|rc))        #  - pre-release letter
                (?P<pre_n>[0-9]+)            #  - pre-release number
            )?
            (?:\.post(?P<post>[0-9]+))?      # post release
            (?:\.dev(?P<dev>[0-9]+))?        # dev release
        )
        (?:\+(?P<local>[a-z0-9]+(?:[a-z0-9\.]*[a-z0-9])?))? # local version
        $
        """,
        re.VERBOSE,
    )

    def __init__(self, version):
        # Validate the version and parse it into pieces
        match = self._regex.search(version)
        if not match:
            raise InvalidVersion("Invalid version: '{0}'".format(version))

        # Store the parsed out pieces of the version
        self._version = _Version(
            epoch=int(match.group("epoch")) if match.group("epoch") else 0,
            release=_parse_dot_version(match.group("release")),
            pre=_parse_pre_version(match.group("pre_l"), match.group("pre_n")),
            post=int(match.group("post")) if match.group("post") else None,
            dev=int(match.group("dev")) if match.group("dev") else None,
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
            parts.append(".post{0}".format(self._version.post))

        # Development release
        if self._version.dev is not None:
            parts.append(".dev{0}".format(self._version.dev))

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


def _parse_dot_version(part):
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


def _parse_pre_version(letter, number):
    if letter and number:
        # We consider the "rc" form of a pre-release to be long-form for the
        # "c" form, thus we normalize "rc" to "c" so we can properly compare
        # them as equal.
        if letter == "rc":
            letter = "c"
        return (letter, int(number))


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

    return (epoch, release, pre, post, dev, local)
