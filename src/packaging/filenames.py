# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.

from __future__ import annotations

import abc
import re
from typing import TYPE_CHECKING, ClassVar, NewType, cast

from .tags import InvalidTag, Tag, UnsortedTagsError, parse_tag
from .version import InvalidVersion, Version, _TrimmedRelease

if TYPE_CHECKING:
    from collections.abc import Iterable

__all__ = [
    "BuildTag",
    "InvalidFilename",
    "InvalidName",
    "InvalidSdistFilename",
    "InvalidWheelFilename",
    "NormalizedName",
    "SourceDistributionFilename",
    "WheelFilename",
    "canonicalize_name",
    "canonicalize_version",
    "is_normalized_name",
]


def __dir__() -> list[str]:
    return __all__


BuildTag = tuple[()] | tuple[int, str]
"""
A wheel build tag: an empty tuple, or a ``(build number, build tag suffix)`` pair.

.. versionadded:: 20.9
"""

NormalizedName = NewType("NormalizedName", str)
"""
A :class:`typing.NewType` of :class:`str`, representing a normalized name.

.. versionadded:: 20.4
"""


class InvalidName(ValueError):
    """
    An invalid distribution name; users should refer to the packaging user guide.

    .. versionadded:: 23.2
    """


class InvalidFilename(ValueError):
    """
    An invalid filename was found, users should refer to the packaging user guide.

    .. versionadded:: 26.4
    """


class InvalidWheelFilename(InvalidFilename):
    """
    An invalid wheel filename was found, users should refer to PEP 427.

    .. versionadded:: 20.9
    """


class InvalidSdistFilename(InvalidFilename):
    """
    An invalid sdist filename was found, users should refer to the packaging user guide.

    .. versionadded:: 20.9
    """


# Core metadata spec for `Name`
_validate_regex = re.compile(
    r"[a-z0-9]|[a-z0-9][a-z0-9._-]*[a-z0-9]", re.IGNORECASE | re.ASCII
)
_normalized_regex = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*", re.ASCII)
# PEP 427: The build number must start with a digit.
_build_tag_regex = re.compile(r"(\d+)(.*)", re.ASCII)
_variant_label_regex = re.compile(r"[0-9a-z._]{1,16}", re.ASCII)
# PEP 427: Valid characters for an escaped project name in a wheel filename.
# Requires at least one character so an empty project name is rejected.
_wheel_name_regex = re.compile(r"^[\w._]+\Z", re.UNICODE)


def canonicalize_name(
    name: str, *, validate: bool = False, underscore: bool = False
) -> NormalizedName:
    """
    This function takes a valid Python package or extra name, and returns the
    normalized form of it.

    The return type is typed as :class:`~packaging.filenames.NormalizedName`.
    This allows type checkers to help require that a string has passed through
    this function before use.

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

    .. versionadded:: 16.2

    .. versionchanged:: 20.4
       The return type was changed to :class:`~packaging.filenames.NormalizedName`.

    .. versionchanged:: 23.2
       Added the *validate* keyword parameter.

    .. versionchanged:: 26.4
       Added the *underscore* keyword parameter.
    """
    if validate and not _validate_regex.fullmatch(name):
        raise InvalidName(f"name is invalid: {name!r}")
    # Ensure all ``.`` and ``_`` are ``-``
    # Emulates ``re.sub(r"[-_.]+", "-", name).lower()`` from PEP 503
    # Much faster than re, and even faster than str.translate
    value = name.lower().replace("_", "-").replace(".", "-")
    # Condense repeats (faster than regex)
    while "--" in value:
        value = value.replace("--", "-")
    if underscore:
        value = value.replace("-", "_")
    return cast("NormalizedName", value)


def is_normalized_name(name: str) -> bool:
    """
    Check if a name is a normalized project name (i.e. a valid name that
    :func:`canonicalize_name` would roundtrip to the same value).

    The roundtrip only characterizes normalized names for *valid* names. A name
    must start and end with an ASCII letter or digit, which
    :func:`canonicalize_name` does not enforce: it leaves a leading or trailing
    hyphen in place, so such a name roundtrips without being normalized.

    :param str name: The name to check.

    >>> from packaging.utils import canonicalize_name, is_normalized_name
    >>> is_normalized_name("requests")
    True
    >>> is_normalized_name("Django")
    False
    >>> canonicalize_name("_not_legal")
    '-not-legal'
    >>> is_normalized_name("-not-legal")  # roundtrips, but not a valid name
    False

    .. versionadded:: 23.2
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

    .. versionadded:: 17.1

    .. versionchanged:: 21.0
       The return type was narrowed to :class:`str`.

    .. versionchanged:: 22.0
       Added the *strip_trailing_zero* keyword parameter.
    """
    if isinstance(version, str):
        try:
            version = Version(version)
        except InvalidVersion:
            return str(version)
    return str(_TrimmedRelease(version) if strip_trailing_zero else version)


def _compress_tag_set(tags: frozenset[Tag]) -> str:
    if not tags:
        msg = "Invalid wheel filename (the tag set must have at least one tag)"
        raise InvalidWheelFilename(msg)
    interpreters = sorted({tag.interpreter for tag in tags})
    abis = sorted({tag.abi for tag in tags})
    platforms = sorted({tag.platform for tag in tags})
    # A compressed tag string always expands to every combination of its fields.
    if len(tags) != len(interpreters) * len(abis) * len(platforms):
        inner = "the tag set cannot be compressed, it must contain every combination"
        msg = f"Invalid wheel filename ({inner}): {sorted(map(str, tags))!r}"
        raise InvalidWheelFilename(msg)
    return "-".join((".".join(interpreters), ".".join(abis), ".".join(platforms)))


class _DistributionFilename(abc.ABC):
    """Shared state and behavior for wheel and sdist filenames."""

    __slots__ = ("_original_name", "_original_version", "_version")

    _error: ClassVar[type[InvalidFilename]]
    _kind: ClassVar[str]

    def __init__(self, name: str, version: str) -> None:
        self._original_name = name
        self._original_version = version
        self._version: Version | None = None

    @classmethod
    def _invalid(cls, inner: str, filename: str | None = None) -> InvalidFilename:
        msg = f"Invalid {cls._kind} filename ({inner})"
        if filename is not None:
            msg = f"{msg}: {filename!r}"
        return cls._error(msg)

    @classmethod
    def _check_normalized(
        cls, name: str, version_part: str, version: Version, filename: str
    ) -> None:
        """Check that the name and version parts are in their normalized form."""
        try:
            cname = canonicalize_name(name, validate=True, underscore=True)
        except InvalidName:
            raise cls._invalid(f"invalid project name {name!r}", filename) from None
        if name != cname:
            raise cls._invalid(f"non-normalized project name {name!r}", filename)
        if version_part != str(version):
            raise cls._invalid(f"non-normalized version {version_part!r}", filename)

    @property
    def original_name(self) -> str:
        """The project name as given."""
        return self._original_name

    @property
    def original_version(self) -> str:
        """The version string as given."""
        return self._original_version

    @property
    def name(self) -> NormalizedName:
        """The normalized project name."""
        return canonicalize_name(self._original_name)

    @property
    def version(self) -> Version:
        """The parsed project version.

        :raises InvalidFilename: If the stored version is not valid.
        """
        if self._version is None:
            try:
                self._version = Version(self._original_version)
            except InvalidVersion as e:
                inner = f"invalid version {self._original_version!r}"
                raise self._invalid(inner) from e
        return self._version

    def _key(self) -> tuple[object, ...]:
        return (self._original_name, self._original_version)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, _DistributionFilename):
            return NotImplemented
        return self._key() == other._key()

    def __hash__(self) -> int:
        return hash(self._key())

    @abc.abstractmethod
    def to_filename(self) -> str: ...

    def __str__(self) -> str:
        return self.to_filename()


class WheelFilename(_DistributionFilename):
    """Represents a wheel filename and its parsed components.

    Instances preserve the original name and version strings for round-tripping,
    while exposing normalized and validated views through properties.

    Instances are immutable and hashable. Two instances are equal if all of their
    original components are equal.

    .. versionadded:: 26.4
    """

    __slots__ = ("_build_tag", "_tags", "_variant")
    __match_args__ = ("name", "version", "build_tag", "tags", "variant")

    _error = InvalidWheelFilename
    _kind = "wheel"

    def __init__(
        self,
        name: str,
        version: str,
        build_tag: BuildTag = (),
        tags: Iterable[Tag] = (),
        variant: str | None = None,
    ) -> None:
        """Create a wheel filename from its component parts.

        :param name: The project name (in original, filename-style form).
        :param version: The version string (in original form).
        :param build_tag: Optional wheel build tag.
        :param tags: The wheel tag set. It must not be empty to make a filename.
        :param variant: The variant label (see :pep:`825`), or ``None``.
        """
        super().__init__(name, version)
        self._build_tag = build_tag
        self._tags = frozenset(tags)
        self._variant = variant

    @property
    def build_tag(self) -> BuildTag:
        """The build tag, or an empty tuple when absent."""
        return self._build_tag

    @property
    def tags(self) -> frozenset[Tag]:
        """The wheel tag set."""
        return self._tags

    @property
    def variant(self) -> str | None:
        """The variant label (see :pep:`825`), or ``None``."""
        return self._variant

    @property
    def compressed_tags(self) -> str:
        """The compressed and sorted wheel tag string (interpreter-abi-platform).

        :raises InvalidWheelFilename: If the tag set is empty, or if it does not
            contain every combination of its interpreters, ABIs, and platforms.

        >>> from packaging.filenames import WheelFilename
        >>> from packaging.tags import Tag
        >>> wf = WheelFilename("foo", "1.0", tags={Tag("py3", "none", "any")})
        >>> wf.compressed_tags
        'py3-none-any'
        >>> tags = {Tag("py3", "none", "any"), Tag("py2", "none", "any")}
        >>> wf = WheelFilename("foo", "1.0", tags=tags)
        >>> wf.compressed_tags
        'py2.py3-none-any'
        """
        return _compress_tag_set(self._tags)

    @property
    def build_str(self) -> str:
        """The build tag as a string, or an empty string when absent.

        >>> from packaging.filenames import WheelFilename
        >>> wf = WheelFilename("foo", "1.0")
        >>> wf.build_str
        ''
        >>> wf = WheelFilename("foo", "1.0", build_tag=(1, "abc"))
        >>> wf.build_str
        '1abc'
        """
        return "".join(map(str, self._build_tag))

    def _key(self) -> tuple[object, ...]:
        return (
            self._original_name,
            self._original_version,
            self._build_tag,
            self._tags,
            self._variant,
        )

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}(name={self._original_name!r}, "
            f"version={self._original_version!r}, "
            f"build_tag={self._build_tag!r}, "
            f"tags={self._tags!r}, "
            f"variant={self._variant!r})"
        )

    def to_filename(self) -> str:
        """
        Combines a project name, version, build tag, tag set, and variant label
        to make a properly formatted wheel filename.

        The project name is normalized such that the non-alphanumeric
        characters are replaced with ``_``. The version is normalized. The
        tag set is compressed into a wheel tag string.

        :raises InvalidWheelFilename: If the version is not valid, or if the tag
            set cannot be compressed (see :attr:`compressed_tags`).

        >>> from packaging.filenames import WheelFilename
        >>> from packaging.tags import Tag
        >>> tags = {Tag("py3", "none", "any")}
        >>> WheelFilename("foo-bar", "1.0", (), tags).to_filename()
        'foo_bar-1.0-py3-none-any.whl'
        """
        name = canonicalize_name(self._original_name, underscore=True)
        file_parts = [name, str(self.version)]
        if self._build_tag:
            file_parts.append(self.build_str)
        file_parts.append(self.compressed_tags)
        if self._variant is not None:
            file_parts.append(self._variant)
        return "-".join(file_parts) + ".whl"

    @classmethod
    def from_filename(
        cls, filename: str, /, *, strict: bool, validate_order: bool = False
    ) -> WheelFilename:
        """
        This function takes the filename of a wheel file, and parses it into a
        :class:`WheelFilename`.

        A filename with six ``-``-separated parts has either a build tag or a
        variant label. It has a build tag if the third part starts with a digit,
        since a Python tag never does. Otherwise, the last part is a variant
        label (see :pep:`825`).

        If **strict** is true, the name, version, build tag, and tags must be in
        their normalized form, which includes sorted tag set components. If
        **validate_order** is true, compressed tag set components are checked to
        be in sorted order as required by PEP 425 even when **strict** is false.

        :param str filename: The name of the wheel file.
        :param bool strict: Require the filename to be fully normalized.
        :param bool validate_order: Check whether compressed tag set components
            are in sorted order.
        :raises InvalidWheelFilename: If the filename in question
            does not follow the :ref:`wheel specification
            <pypug:binary-distribution-format>`.

        >>> from packaging.filenames import WheelFilename
        >>> from packaging.tags import Tag
        >>> wf = WheelFilename.from_filename("foo-1.0-py3-none-any.whl", strict=True)
        >>> wf.name
        'foo'
        >>> wf.version
        <Version('1.0')>
        >>> wf.build_tag
        ()
        >>> wf.tags == {Tag("py3", "none", "any")}
        True
        """
        if not filename.endswith(".whl"):
            raise cls._invalid("extension must be '.whl'", filename)

        parts = filename[:-4].split("-")
        if len(parts) not in {5, 6, 7}:
            raise cls._invalid("wrong number of parts", filename)

        name, version_part, *rest = parts

        # Six parts are ambiguous: a build tag or a variant label (PEP 825).
        # A build tag starts with a digit, and a Python tag never does.
        build_match = _build_tag_regex.match(rest[0]) if len(rest) > 3 else None
        if len(rest) == 5 and build_match is None:
            raise cls._invalid(f"invalid build number {rest[0]!r}", filename)
        build_part = rest.pop(0) if build_match else None
        variant = rest.pop() if len(rest) == 4 else None
        tag_str = "-".join(rest)

        try:
            tags = parse_tag(tag_str, validate_order=validate_order or strict)
        except UnsortedTagsError:
            inner = "compressed tag set components must be in sorted order per PEP 425"
            raise cls._invalid(inner, filename) from None
        except InvalidTag:
            raise cls._invalid(f"invalid tag component {tag_str!r}", filename) from None

        # See PEP 427 for the rules on escaping the project name.
        if "__" in name or _wheel_name_regex.match(name) is None:
            raise cls._invalid(f"invalid project name {name!r}", filename)

        try:
            version = Version(version_part)
        except InvalidVersion as e:
            raise cls._invalid(f"invalid version {version_part!r}", filename) from e

        build_tag: BuildTag = ()
        if build_match is not None:
            build_tag = (int(build_match.group(1)), build_match.group(2))

        if variant is not None and _variant_label_regex.fullmatch(variant) is None:
            raise cls._invalid(f"invalid variant label {variant!r}", filename)

        self = cls(name, version_part, build_tag, tags, variant)
        self._version = version

        # Reconstruct the filename and check that it matches the original
        if strict:
            cls._check_normalized(name, version_part, version, filename)
            if build_part is not None and build_part != self.build_str:
                inner = f"non-normalized build tag {build_part!r}"
                raise cls._invalid(inner, filename)
            if self.compressed_tags != tag_str:
                raise cls._invalid(f"non-normalized tags {tag_str!r}", filename)

        return self


class SourceDistributionFilename(_DistributionFilename):
    """Represents a source distribution filename and its parsed components.

    Instances preserve the original name and version strings for round-tripping,
    while exposing normalized and validated views through properties.

    Instances are immutable and hashable. Two instances are equal if their
    original name and version are equal.

    .. versionadded:: 26.4
    """

    __slots__ = ()
    __match_args__ = ("name", "version")

    _error = InvalidSdistFilename
    _kind = "sdist"

    def __init__(self, name: str, version: str) -> None:
        """Create a source distribution filename from name and version.

        :param str name: The project name (in original, filename-style form).
        :param str version: The version string (in original form).
        """
        super().__init__(name, version)

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}(name={self._original_name!r}, "
            f"version={self._original_version!r})"
        )

    def to_filename(self) -> str:
        """
        Combines the project name and a version to make a valid sdist filename. The
        project name is normalized as required so that any run of ``-._``
        characters are replaced with ``_`` and characters are lower cased. The
        version is normalized.

        :raises InvalidSdistFilename: If the version is not valid.

        >>> from packaging.filenames import SourceDistributionFilename
        >>> SourceDistributionFilename("foo-bar", "1.0").to_filename()
        'foo_bar-1.0.tar.gz'
        """
        name = canonicalize_name(self._original_name, underscore=True)
        return f"{name}-{self.version}.tar.gz"

    @classmethod
    def from_filename(
        cls, filename: str, /, *, strict: bool
    ) -> SourceDistributionFilename:
        """
        This function takes the filename of a sdist file (as specified
        in the `Source distribution format`_ documentation), and parses
        it into a :class:`SourceDistributionFilename`.

        :param str filename: The name of the sdist file.
        :param bool strict: Require a ``.tar.gz`` extension and a fully
            normalized name and version.
        :raises InvalidSdistFilename: If the filename does not end
            with an sdist extension (``.zip`` or ``.tar.gz``), if it does not
            contain a dash separating the name and the version of the distribution,
            if the project name is empty, or if the version portion is not a valid
            version.

        >>> from packaging.filenames import SourceDistributionFilename
        >>> fn = SourceDistributionFilename.from_filename("foo-1.0.tar.gz", strict=True)
        >>> fn.name
        'foo'
        >>> fn.version
        <Version('1.0')>

        .. _Source distribution format: https://packaging.python.org/specifications/source-distribution-format/#source-distribution-file-name
        """
        # PEP 625: Source distributions must end with .tar.gz
        # Non-strict mode will allow .zip for backward compatibility
        if filename.endswith(".tar.gz"):
            file_stem = filename[: -len(".tar.gz")]
        elif filename.endswith(".zip") and not strict:
            file_stem = filename[: -len(".zip")]
        else:
            extensions = "'.tar.gz'" if strict else "'.tar.gz' or '.zip'"
            raise cls._invalid(f"extension must be {extensions}", filename)

        # PEP 625: Source distributions may only have one hyphen, separating
        # the name and version. Strict mode rejects extra hyphens via the
        # normalized name check below.
        name_part, sep, version_part = file_stem.rpartition("-")
        if not sep:
            inner = "hyphen must separate name and version parts"
            raise cls._invalid(inner, filename)
        if not name_part:
            raise cls._invalid("empty project name", filename)

        try:
            version = Version(version_part)
        except InvalidVersion as e:
            raise cls._invalid(f"invalid version {version_part!r}", filename) from e

        if strict:
            cls._check_normalized(name_part, version_part, version, filename)

        self = cls(name_part, version_part)
        self._version = version
        return self
