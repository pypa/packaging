# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.

from __future__ import annotations

from typing import TYPE_CHECKING

from .filenames import (
    BuildTag,
    InvalidName,
    InvalidSdistFilename,
    InvalidWheelFilename,
    NormalizedName,
    SourceDistributionFilename,
    WheelFilename,
    canonicalize_name,
    canonicalize_version,
    is_normalized_name,
)

if TYPE_CHECKING:
    from .tags import Tag
    from .version import Version

# For historical reasons, we export the filename parsing functions from this
# module, even though they are implemented in the filenames module now.

__all__ = [
    "BuildTag",
    "InvalidName",
    "InvalidSdistFilename",
    "InvalidWheelFilename",
    "NormalizedName",
    "canonicalize_name",
    "canonicalize_version",
    "is_normalized_name",
    "parse_sdist_filename",
    "parse_wheel_filename",
]


def __dir__() -> list[str]:
    return __all__


def parse_wheel_filename(
    filename: str,
    *,
    validate_order: bool = False,
) -> tuple[NormalizedName, Version, BuildTag, frozenset[Tag]]:
    """
    This function takes the filename of a wheel file, and parses it,
    returning a tuple of name, version, build number, and tags.

    The name part of the tuple is normalized and typed as
    :class:`~packaging.filenames.NormalizedName`. The version portion is an
    instance of :class:`~packaging.version.Version`. The build number is ``()`` if
    there is no build number in the wheel filename, otherwise a
    two-item tuple of an integer for the leading digits and
    a string for the rest of the build number. The tags portion is a
    frozen set of :class:`~packaging.tags.Tag` instances (as the tag
    string format allows multiple tags to be combined into a single
    string).

    If **validate_order** is true, compressed tag set components are
    checked to be in sorted order as required by PEP 425.

    :param str filename: The name of the wheel file.
    :param bool validate_order: Check whether compressed tag set components
        are in sorted order.
    :raises InvalidWheelFilename: If the filename in question
        does not follow the :ref:`wheel specification
        <pypug:binary-distribution-format>`.

    >>> from packaging.utils import parse_wheel_filename
    >>> from packaging.tags import Tag
    >>> from packaging.version import Version
    >>> name, ver, build, tags = parse_wheel_filename("foo-1.0-py3-none-any.whl")
    >>> name
    'foo'
    >>> ver == Version('1.0')
    True
    >>> tags == {Tag("py3", "none", "any")}
    True
    >>> not build
    True

    .. versionadded:: 20.9

    .. versionchanged:: 23.2
       Raises :class:`InvalidWheelFilename` when the version component is invalid.

    .. versionadded:: 26.1
       The *validate_order* parameter.

    .. versionchanged:: 26.3
       Raises :class:`InvalidWheelFilename` when an interpreter component is
       not an identifier, a tag set component is empty, or the project name is
       empty.
    """
    fname = WheelFilename.from_filename(
        filename, strict=False, validate_order=validate_order
    )
    return (fname.name, fname.version, fname.build_tag, fname.tags)


def parse_sdist_filename(filename: str) -> tuple[NormalizedName, Version]:
    """
    This function takes the filename of a sdist file (as specified
    in the `Source distribution format`_ documentation), and parses
    it, returning a tuple of the normalized name and version as
    represented by an instance of :class:`~packaging.version.Version`.

    :param str filename: The name of the sdist file.
    :raises InvalidSdistFilename: If the filename does not end
        with an sdist extension (``.zip`` or ``.tar.gz``), if it does not
        contain a dash separating the name and the version of the distribution,
        if the project name is empty, or if the version portion is not a valid
        version.

    >>> from packaging.utils import parse_sdist_filename
    >>> from packaging.version import Version
    >>> name, ver = parse_sdist_filename("foo-1.0.tar.gz")
    >>> name
    'foo'
    >>> ver == Version('1.0')
    True

    .. versionadded:: 20.9

    .. versionchanged:: 21.0
       Added support for ``.zip`` source distributions.

    .. versionchanged:: 23.2
       Raises :class:`InvalidSdistFilename` when the version component is invalid.

    .. versionchanged:: 26.3
       Raises :class:`InvalidSdistFilename` on an empty project name.

    .. _Source distribution format: https://packaging.python.org/specifications/source-distribution-format/#source-distribution-file-name
    """
    fname = SourceDistributionFilename.from_filename(filename, strict=False)
    return (fname.name, fname.version)
