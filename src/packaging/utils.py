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
    SourceFilename,
    WheelFilename,
    canonicalize_name,
    canonicalize_version,
    is_normalized_name,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

    from .tags import Tag
    from .version import Version

__all__ = [
    "BuildTag",
    "InvalidName",
    "InvalidSdistFilename",
    "InvalidWheelFilename",
    "NormalizedName",
    "canonicalize_name",
    "canonicalize_version",
    "compose_sdist_filename",
    "compose_wheel_filename",
    "is_normalized_name",
    "parse_sdist_filename",
    "parse_wheel_filename",
]


def __dir__() -> list[str]:
    return __all__


def compose_wheel_filename(
    name: str, version: Version, build: BuildTag | None, tags: Iterable[Tag]
) -> str:
    """
    Combines a project name, version, build tag, and tag set
    to make a properly formatted wheel filename.

    The project name is normalized such that the non-alphanumeric
    characters are replaced with ``_``. The version is an instance of
    :class:`~packaging.version.Version`. The build tag can be None,
    an empty tuple or a two-item tuple of an integer and a string.
    The tags is set of tags that will be compressed into a wheel
    tag string.

    :param name: The project name
    :param version: The project version
    :param build: An optional two-item tuple of an integer and string
    :param tags: The set of tags that apply to the wheel

    >>> from packaging.utils import compose_wheel_filename
    >>> from packaging.tags import Tag
    >>> from packaging.version import Version
    >>> version = Version("1.0")
    >>> tags = {Tag("py3", "none", "any")}
    >>> compose_wheel_filename("foo-bar", version, None, tags)
    'foo_bar-1.0-py3-none-any.whl'

    .. versionadded:: 26.1
    """
    filename = WheelFilename(
        name=name,
        version=str(version),
        build_tag=build or (),
        tags=tags,
    )
    return str(filename)


def parse_wheel_filename(
    filename: str,
) -> tuple[NormalizedName, Version, BuildTag, frozenset[Tag]]:
    """
    This function takes the filename of a wheel file, and parses it,
    returning a tuple of name, version, build number, and tags.

    The name part of the tuple is normalized and typed as
    :class:`NormalizedName`. The version portion is an instance of
    :class:`~packaging.version.Version`. The build number is ``()`` if
    there is no build number in the wheel filename, otherwise a
    two-item tuple of an integer for the leading digits and
    a string for the rest of the build number. The tags portion is a
    frozen set of :class:`~packaging.tags.Tag` instances (as the tag
    string format allows multiple tags to be combined into a single
    string).

    :param str filename: The name of the wheel file.
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
    """
    fname = WheelFilename.from_filename(filename)
    return (fname.name, fname.version, fname.build_tag, fname.tags)


def compose_sdist_filename(name: str, version: Version) -> str:
    """
    Combines the project name and a version to make a valid sdist filename. The
    project name is normalized as required so that any run of ``-._``
    characters are replaced with ``_`` and characters are lower cased. The
    version is an instance of :class:`~packaging.version.Version`.

    :param name: The project name
    :param version: The project version

    >>> from packaging.utils import compose_sdist_filename
    >>> from packaging.version import Version
    >>> "foo_bar-1.0.tar.gz" == compose_sdist_filename("foo-bar", Version("1.0"))
    True

    .. versionadded:: 26.1
    """
    filename = SourceFilename(
        name=name,
        version=str(version),
    )
    return str(filename)


def parse_sdist_filename(filename: str) -> tuple[NormalizedName, Version]:
    """
    This function takes the filename of a sdist file (as specified
    in the `Source distribution format`_ documentation), and parses
    it, returning a tuple of the normalized name and version as
    represented by an instance of :class:`~packaging.version.Version`.

    :param str filename: The name of the sdist file.
    :raises InvalidSdistFilename: If the filename does not end
        with an sdist extension (``.zip`` or ``.tar.gz``), or if it does not
        contain a dash separating the name and the version of the distribution.

    >>> from packaging.utils import parse_sdist_filename
    >>> from packaging.version import Version
    >>> name, ver = parse_sdist_filename("foo-1.0.tar.gz")
    >>> name
    'foo'
    >>> ver == Version('1.0')
    True

    .. _Source distribution format: https://packaging.python.org/specifications/source-distribution-format/#source-distribution-file-name
    """
    fname = SourceFilename.from_filename(filename)
    return (fname.name, fname.version)
