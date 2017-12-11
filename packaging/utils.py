# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.
from __future__ import absolute_import, division, print_function

import re

from .version import Version, InvalidVersion

_canonicalize_regex = re.compile(r"[-_.]+")


def canonicalize_name(name):
    # This is taken from PEP 503.
    return _canonicalize_regex.sub("-", name).lower()


def safe_extra(extra):
    """Convert an arbitrary string to a standard 'extra' name

    Any runs of non-alphanumeric characters are replaced with a single '_',
    and the result is always lowercased.
    """
    return re.sub('[^A-Za-z0-9.-]+', '_', extra).lower()


def safe_name(name):
    """Convert an arbitrary string to a standard distribution name

    Any runs of non-alphanumeric/. characters are replaced with a single '-'.
    """
    return re.sub('[^A-Za-z0-9.]+', '-', name)


def safe_version(version):
    """
    Convert an arbitrary string to a standard version string
    """
    try:
        # normalize the version
        return str(Version(version))
    except InvalidVersion:
        version = version.replace(' ', '.')
        return re.sub('[^A-Za-z0-9.]+', '-', version)
