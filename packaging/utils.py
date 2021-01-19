# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.
from __future__ import absolute_import, division, print_function

import re

from ._typing import TYPE_CHECKING, cast
from .tags import Tag, parse_tag
from .version import InvalidVersion, Version

if TYPE_CHECKING:  # pragma: no cover
    from typing import FrozenSet, NewType, Optional, Tuple, Union

    NormalizedName = NewType("NormalizedName", str)
else:
    NormalizedName = str


class InvalidWheelFilename(ValueError):
    """
    An invalid wheel filename was found, users should refer to PEP 427.
    """


class InvalidSdistFilename(ValueError):
    """
    An invalid sdist filename was found, users should refer to the packaging user guide.
    """


_canonicalize_regex = re.compile(r"[-_.]+")


def canonicalize_name(name):
    # type: (str) -> NormalizedName
    # This is taken from PEP 503.
    value = _canonicalize_regex.sub("-", name).lower()
    return cast("NormalizedName", value)


def canonicalize_version(version):
    # type: (Union[Version, str]) -> Union[Version, str]
    """
    This is very similar to Version.__str__, but has one subtle difference
    with the way it handles the release segment.
    """
    if not isinstance(version, Version):
        try:
            version = Version(version)
        except InvalidVersion:
            # Legacy versions cannot be normalized
            return version

    parts = []

    # Epoch
    if version.epoch != 0:
        parts.append("{0}!".format(version.epoch))

    # Release segment
    # NB: This strips trailing '.0's to normalize
    parts.append(re.sub(r"(\.0)+$", "", ".".join(str(x) for x in version.release)))

    # Pre-release
    if version.pre is not None:
        parts.append("".join(str(x) for x in version.pre))

    # Post-release
    if version.post is not None:
        parts.append(".post{0}".format(version.post))

    # Development release
    if version.dev is not None:
        parts.append(".dev{0}".format(version.dev))

    # Local version segment
    if version.local is not None:
        parts.append("+{0}".format(version.local))

    return "".join(parts)


def parse_wheel_filename(filename):
    # type: (str) -> Tuple[NormalizedName, Version, Optional[str], FrozenSet[Tag]]
    if not filename.endswith(".whl"):
        raise InvalidWheelFilename(
            "Invalid wheel filename (extension must be '.whl'): {0}".format(filename)
        )

    filename = filename[:-4]
    dashes = filename.count("-")
    if dashes not in (4, 5):
        raise InvalidWheelFilename(
            "Invalid wheel filename (wrong number of parts): {0}".format(filename)
        )

    parts = filename.split("-", dashes - 2)
    name = canonicalize_name(parts[0])
    version = Version(parts[1])
    if dashes == 5:
        # Build number must start with a digit
        build_part = parts[2]
        if not build_part[0].isdigit():
            raise InvalidWheelFilename(
                "Invalid build number: {0} in '{1}'".format(build_part, filename)
            )
        build = build_part  # type: Optional[str]
    else:
        build = None
    tags = parse_tag(parts[-1])
    return (name, version, build, tags)


def parse_sdist_filename(filename):
    # type: (str) -> Tuple[NormalizedName, Version]
    if not filename.endswith(".tar.gz"):
        raise InvalidSdistFilename(
            "Invalid sdist filename (extension must be '.tar.gz'): {0}".format(filename)
        )

    # We are requiring a PEP 440 version, which cannot contain dashes,
    # so we split on the last dash.
    name_part, sep, version_part = filename[:-7].rpartition("-")
    if not sep:
        raise InvalidSdistFilename("Invalid sdist filename: {0}".format(filename))

    name = canonicalize_name(name_part)
    version = Version(version_part)
    return (name, version)
