from __future__ import annotations

import re
from typing import TYPE_CHECKING, NewType, Tuple, Union, cast

from .tags import Tag, parse_tag
from .version import InvalidVersion, Version, _TrimmedRelease

if TYPE_CHECKING:
    from collections.abc import Iterable

__all__ = [
    "BuildTag",
    "InvalidFilename",
    "InvalidName",
    "InvalidSdistFilename",
    "InvalidSdistFilename",
    "InvalidWheelFilename",
    "InvalidWheelFilename",
    "NormalizedName",
    "SourceFilename",
    "WheelFilename",
    "canonicalize_name",
    "canonicalize_version",
    "is_normalized_name",
]


def __dir__() -> list[str]:
    return __all__


BuildTag = Union[Tuple[()], Tuple[int, str]]

NormalizedName = NewType("NormalizedName", str)
"""
A :class:`typing.NewType` of :class:`str`, representing a normalized name.
"""


class InvalidName(ValueError):
    """
    An invalid distribution name; users should refer to the packaging user guide.
    """


class InvalidFilename(ValueError):
    """
    .
    """


class InvalidWheelFilename(InvalidFilename):
    """
    An invalid wheel filename was found, users should refer to PEP 427.
    """


class InvalidSdistFilename(InvalidFilename):
    """
    An invalid sdist filename was found, users should refer to the packaging user guide.
    """


# Core metadata spec for `Name`
_validate_regex = re.compile(
    r"[a-z0-9]|[a-z0-9][a-z0-9._-]*[a-z0-9]", re.IGNORECASE | re.ASCII
)
_normalized_regex = re.compile(r"[a-z0-9]|[a-z0-9]([a-z0-9-](?!--))*[a-z0-9]", re.ASCII)
# PEP 427: The build number must start with a digit.
_build_tag_regex = re.compile(r"(\d+)(.*)", re.ASCII)


def canonicalize_name(
    name: str, *, validate: bool = False, underscore: bool = False
) -> NormalizedName:
    """
    This function takes a valid Python package or extra name, and returns the
    normalized form of it.

    The return type is typed as :class:`NormalizedName`. This allows type
    checkers to help require that a string has passed through this function
    before use.

    If **validate** is true, then the function will check if **name** is a valid
    distribution name before normalizing. If **underscore** is true, then hyphens
    will be replaced with underscores instead of hyphens (such as for a filename).

    :param str name: The name to normalize.
    :param bool validate: Check whether the name is a valid distribution name.
    :param bool underscore: Replace hyphens with underscores instead of hyphens.
    :raises InvalidName: If **validate** is true and the name is not an
        acceptable distribution name.

    >>> from packaging.utils import canonicalize_name
    >>> canonicalize_name("Django")
    'django'
    >>> canonicalize_name("oslo.concurrency")
    'oslo-concurrency'
    >>> canonicalize_name("oslo.concurrency", underscore=True)
    'oslo_concurrency'
    >>> canonicalize_name("requests")
    'requests'
    """
    if validate and not _validate_regex.fullmatch(name):
        raise InvalidName(f"name is invalid: {name!r}")
    if underscore:
        value = name.lower().replace("-", "_").replace(".", "_")
        while "__" in value:
            value = value.replace("__", "_")
    else:
        # Ensure all ``.`` and ``_`` are ``-``
        # Emulates ``re.sub(r"[-_.]+", "-", name).lower()`` from PEP 503
        # Much faster than re, and even faster than str.translate
        value = name.lower().replace("_", "-").replace(".", "-")
        # Condense repeats (faster than regex)
        while "--" in value:
            value = value.replace("--", "-")
    return cast("NormalizedName", value)


def is_normalized_name(name: str) -> bool:
    """
    Check if a name is already normalized (i.e. :func:`canonicalize_name` would
    roundtrip to the same value).

    :param str name: The name to check.

    >>> from packaging.utils import is_normalized_name
    >>> is_normalized_name("requests")
    True
    >>> is_normalized_name("Django")
    False
    """
    return _normalized_regex.fullmatch(name) is not None


def canonicalize_version(
    version: Version | str, *, strip_trailing_zero: bool = True
) -> str:
    """Return a canonical form of a version as a string.

    This function takes a string representing a package version (or a
    :class:`~packaging.version.Version` instance), and returns the
    normalized form of it. By default, it strips trailing zeros from
    the release segment.

    >>> from packaging.utils import canonicalize_version
    >>> canonicalize_version('1.0.1')
    '1.0.1'

    Per PEP 625, versions may have multiple canonical forms, differing
    only by trailing zeros.

    >>> canonicalize_version('1.0.0')
    '1'
    >>> canonicalize_version('1.0.0', strip_trailing_zero=False)
    '1.0.0'

    Invalid versions are returned unaltered.

    >>> canonicalize_version('foo bar baz')
    'foo bar baz'

    >>> canonicalize_version('1.4.0.0.0')
    '1.4'
    """
    if isinstance(version, str):
        try:
            version = Version(version)
        except InvalidVersion:
            return str(version)
    return str(_TrimmedRelease(version) if strip_trailing_zero else version)


def _join_tag_attr(tags: Iterable[Tag], field: str) -> str:
    return ".".join(sorted({getattr(tag, field) for tag in tags}))


def _compress_tag_set(tags: Iterable[Tag]) -> str:
    return "-".join(_join_tag_attr(tags, x) for x in ("interpreter", "abi", "platform"))


class WheelFilename:
    __slots__ = ("build_tag", "original_name", "original_version", "tags")

    def __init__(
        self,
        name: str,
        version: str,
        build_tag: BuildTag = (),
        tags: Iterable[Tag] = (),
    ) -> None:
        self.original_name = name
        self.original_version = version
        self.build_tag = build_tag
        self.tags = frozenset(tags)

    @property
    def name(self) -> NormalizedName:
        return canonicalize_name(self.original_name)

    @property
    def version(self) -> Version:
        try:
            return Version(self.original_version)
        except InvalidVersion as e:
            msg = f"Invalid wheel filename (invalid version {self.original_version!r})"
            raise InvalidWheelFilename(msg) from e

    @property
    def compressed_tags(self) -> str:
        return _compress_tag_set(self.tags)

    @property
    def build_str(self) -> str:
        return "".join(map(str, self.build_tag))

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}(name={self.original_name!r}, "
            f"version={self.original_version!r}, "
            f"build_tag={self.build_tag!r}, "
            f"tags={self.tags!r})"
        )

    def __str__(self) -> str:
        return self.to_filename()

    def to_filename(self) -> str:
        """
        Combines a project name, version, build tag, and tag set
        to make a properly formatted wheel filename.

        The project name is normalized such that the non-alphanumeric
        characters are replaced with ``_``. The version is an instance of
        :class:`~packaging.version.Version`. The build tag can be None,
        an empty tuple or a two-item tuple of an integer and a string.
        The tags is set of tags that will be compressed into a wheel
        tag string.

        >>> from packaging.utils import compose_wheel_filename
        >>> from packaging.tags import Tag
        >>> from packaging.version import Version
        >>> version = Version("1.0")
        >>> tags = {Tag("py3", "none", "any")}
        >>> compose_wheel_filename("foo-bar", version, None, tags)
        'foo_bar-1.0-py3-none-any.whl'

        .. versionadded:: 26.1
        """

        ctags = self.compressed_tags
        name = canonicalize_name(self.original_name, underscore=True)
        if self.build_tag:
            return f"{name}-{self.version}-{self.build_str}-{ctags}.whl"
        else:
            return f"{name}-{self.version}-{ctags}.whl"

    @classmethod
    def from_filename(cls, filename: str, /, *, strict: bool) -> WheelFilename:
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
        if not filename.endswith(".whl"):
            msg = f"Invalid wheel filename (extension must be '.whl'): {filename!r}"
            raise InvalidWheelFilename(msg)

        filestem = filename[:-4]
        dashes = filestem.count("-")
        if dashes not in (4, 5):
            msg = f"Invalid wheel filename (wrong number of parts): {filename!r}"
            raise InvalidWheelFilename(msg)

        parts = filestem.split("-", dashes - 2)
        name = parts[0]
        version = parts[1]
        tags = parse_tag(parts[-1])

        # See PEP 427 for the rules on escaping the project name.
        if "__" in name or re.match(r"^[\w\d._]*$", name, re.UNICODE) is None:
            inner = f"invalid project name: {name!r}"
            msg = f"Invalid wheel filename ({inner}): {filename!r}"
            raise InvalidWheelFilename(msg)

        try:
            Version(version)
        except InvalidVersion:
            inner = f"invalid version: {version!r}"
            msg = f"Invalid wheel filename ({inner}): {filename!r}"
            raise InvalidWheelFilename(msg) from None

        if dashes == 5:
            build_part = parts[2]
            build_match = _build_tag_regex.match(build_part)
            if build_match is None:
                inner = f"invalid build number: {build_part!r}"
                msg = f"Invalid wheel filename ({inner}): {filename!r}"
                raise InvalidWheelFilename(msg)
            build_tag = cast(
                "BuildTag", (int(build_match.group(1)), build_match.group(2))
            )
        else:
            build_tag = ()

        self = cls(name, version, build_tag, tags)

        # Reconstruct the filename and check that it matches the original
        if strict:
            if self.original_name != canonicalize_name(
                self.original_name, underscore=True
            ):
                inner = f"non-normalized project name {self.original_name!r}"
                msg = f"Invalid wheel filename ({inner}): {filename!r}"
                raise InvalidWheelFilename(msg)
            if self.original_version != str(self.version):
                inner = f"non-normalized version {self.original_version!r}"
                msg = f"Invalid wheel filename ({inner}): {filename!r}"
                raise InvalidWheelFilename(msg)

        return self


class SourceFilename:
    __slots__ = ("original_name", "original_version")

    def __init__(self, name: str, version: str) -> None:
        # Store the values that were originally passed for use externally
        self.original_name = name
        self.original_version = version

    @property
    def name(self) -> NormalizedName:
        return canonicalize_name(self.original_name)

    @property
    def version(self) -> Version:
        try:
            return Version(self.original_version)
        except InvalidVersion as e:
            raise InvalidSdistFilename(
                f"Invalid filename (invalid version {self.original_version!r})"
            ) from e

    def to_filename(self) -> str:
        """
        Combines the project name and a version to make a valid sdist filename. The
        project name is normalized as required so that any run of ``-._``
        characters are replaced with ``_`` and characters are lower cased. The
        version is an instance of :class:`~packaging.version.Version`.

        >>> from packaging.utils import compose_sdist_filename
        >>> from packaging.version import Version
        >>> "foo_bar-1.0.tar.gz" == compose_sdist_filename("foo-bar", Version("1.0"))
        True

        .. versionadded:: 26.1
        """
        name = canonicalize_name(self.original_name, underscore=True)
        version = str(self.version)

        return f"{name}-{version}.tar.gz"

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}(name={self.original_name!r}, "
            f"version={self.original_version!r})"
        )

    def __str__(self) -> str:
        return self.to_filename()

    @classmethod
    def from_filename(cls, filename: str, /, *, strict: bool) -> SourceFilename:
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
        # PEP 625: Source distributions must end with .tar.gz
        # Non-scrict mode will allow .zip for backward compatibility
        if filename.endswith(".tar.gz"):
            file_stem = filename[: -len(".tar.gz")]
        elif filename.endswith(".zip") and not strict:
            file_stem = filename[: -len(".zip")]
        else:
            raise InvalidSdistFilename(
                f"Invalid SDist filename (extension must be '.tar.gz'): {filename!r}"
            )

        name_part, sep, version_part = file_stem.rpartition("-")
        # PEP 625: Source distributions may only have one hyphen, separating
        # the name and version
        if strict and "-" in name_part:
            inner = "name and version parts can not contain hyphens"
            msg = f"Invalid SDist filename ({inner}): {filename!r}"
            raise InvalidSdistFilename(msg)

        if not sep:
            inner = "hyphen must separate name and version parts"
            msg = f"Invalid SDist filename ({inner}): {filename!r}"
            raise InvalidSdistFilename(msg)

        try:
            Version(version_part)
        except InvalidVersion as e:
            inner = f"invalid version {version_part!r}"
            msg = f"Invalid SDist filename ({inner}): {filename!r}"
            raise InvalidSdistFilename(msg) from e

        if strict:
            try:
                cname = canonicalize_name(name_part, validate=True, underscore=True)
            except InvalidName:
                inner = f"invalid project name {name_part!r}"
                msg = f"Invalid SDist filename ({inner}): {filename!r}"
                raise InvalidSdistFilename(msg) from None
            if name_part != cname:
                inner = f"non-normalized project name {name_part!r}"
                msg = f"Invalid SDist filename ({inner}): {filename!r}"
                raise InvalidSdistFilename(msg)
            if version_part != str(Version(version_part)):
                inner = f"non-normalized version {version_part!r}"
                msg = f"Invalid SDist filename ({inner}): {filename!r}"
                raise InvalidSdistFilename(msg) from None

        return cls(name_part, version_part)
