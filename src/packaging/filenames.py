# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.

from __future__ import annotations

import re
from typing import TYPE_CHECKING, TypedDict

from .errors import _ErrorCollector
from .tags import InvalidTag, Tag, parse_tag
from .utils import (
    BuildTag,
    InvalidFilename,
    InvalidName,
    InvalidSdistFilename,
    InvalidWheelFilename,
    UnsortedWheelTags,
    _parse_build_tag,
    _parse_sdist_filename,
    _parse_wheel_filename,
    _split_wheel_filename,
    _validate_regex,
    _variant_label_regex,
    canonicalize_name,
)
from .version import InvalidVersion, Version

if TYPE_CHECKING:
    from collections.abc import Iterable

    from typing_extensions import Self, Unpack

    from .utils import NormalizedName

__all__ = [
    "BuildTag",
    "InvalidFilename",
    "InvalidProjectName",
    "InvalidSdistFilename",
    "InvalidWheelFilename",
    "NonNormalizedBuildTag",
    "NonNormalizedName",
    "NonNormalizedTags",
    "NonNormalizedVersion",
    "SourceDistributionFilename",
    "UnsortedWheelTags",
    "WheelFilename",
]


def __dir__() -> list[str]:
    return __all__


class InvalidProjectName(InvalidFilename):
    """
    The project name in a filename can be parsed, but is not a valid project
    name.

    .. versionadded:: 26.4
    """


class NonNormalizedName(InvalidFilename):
    """
    The project name in a filename is valid, but not normalized.

    .. versionadded:: 26.4
    """


class NonNormalizedVersion(InvalidFilename):
    """
    The version in a filename is valid, but not normalized.

    .. versionadded:: 26.4
    """


class NonNormalizedBuildTag(InvalidWheelFilename):
    """
    The build tag in a wheel filename is valid, but not normalized.

    .. versionadded:: 26.4
    """


class NonNormalizedTags(InvalidWheelFilename):
    """
    The tags in a wheel filename are valid, but not normalized.

    .. versionadded:: 26.4
    """


class _SdistReplace(TypedDict, total=False):
    name: str
    version: Version | str


class _WheelReplace(TypedDict, total=False):
    name: str
    version: Version | str
    build_tag: BuildTag
    tags: Iterable[Tag]
    variant: str | None


# A name in the normalized filename form, where "-" is written as "_".
_normalized_wheel_name_regex = re.compile(r"[a-z0-9]+(?:_[a-z0-9]+)*", re.ASCII)
# A release-only version with no leading zeros, which is always normalized.
_normalized_release_regex = re.compile(r"(?:0|[1-9][0-9]*)(?:\.(?:0|[1-9][0-9]*))*")


def _is_normalized_version(version_part: str, version: Version) -> bool:
    # str(version) is slow, so check the common case first.
    return _normalized_release_regex.fullmatch(
        version_part
    ) is not None or version_part == str(version)


def _compress_tags(tags: frozenset[Tag]) -> str:
    if not tags:
        msg = "Invalid wheel filename (the tag set must have at least one tag)"
        raise InvalidWheelFilename(msg)
    interpreters = sorted({tag.interpreter for tag in tags})
    abis = sorted({tag.abi for tag in tags})
    platforms = sorted({tag.platform for tag in tags})
    # A compressed tag string always expands to every combination of its fields.
    if len(tags) != len(interpreters) * len(abis) * len(platforms):
        msg = (
            "Invalid wheel filename (the tag set cannot be compressed, it must "
            f"contain every combination: {sorted(map(str, tags))!r})"
        )
        raise InvalidWheelFilename(msg)
    return "-".join((".".join(interpreters), ".".join(abis), ".".join(platforms)))


class WheelFilename:
    """Represents a wheel filename and its parsed components.

    Instances are immutable and hashable. Two instances are equal if their
    normalized name, normalized version, build tag, tags, and variant are equal.

    Instances are safe to serialize with :mod:`pickle`. They use a stable
    format so the same pickle can be loaded in future packaging releases.

    .. versionadded:: 26.4
    """

    __slots__ = ("_build_tag", "_filename", "_name", "_tags", "_variant", "_version")
    __match_args__ = ("name", "version", "tags")

    def __init__(
        self,
        name: str,
        version: Version | str,
        tags: Iterable[Tag],
        *,
        build_tag: BuildTag = (),
        variant: str | None = None,
    ) -> None:
        """Create a wheel filename from its component parts.

        :param name: The project name. It is stored in normalized form.
        :param version: The version.
        :param tags: The wheel tag set. It must not be empty, and it must
            contain every combination of its interpreters, ABIs, and platforms.
            Each tag must be valid in a filename (see
            :func:`~packaging.tags.parse_tag`).
        :param build_tag: Optional wheel build tag.
        :param variant: The variant label (see :pep:`825`), or ``None``.
        :raises InvalidWheelFilename: If the name, version, tag set, build tag,
            or variant label is not valid.
        """
        self._filename: str | None = None
        self._set(
            name=name, version=version, tags=tags, build_tag=build_tag, variant=variant
        )

    def _set(self, **kwargs: Unpack[_WheelReplace]) -> None:
        if "name" in kwargs:
            name = kwargs["name"]
            try:
                self._name = canonicalize_name(name, validate=True)
            except InvalidName:
                msg = f"Invalid wheel filename (invalid project name {name!r})"
                raise InvalidWheelFilename(msg) from None
        if "version" in kwargs:
            version = kwargs["version"]
            try:
                self._version = (
                    version if isinstance(version, Version) else Version(version)
                )
            except InvalidVersion as e:
                msg = f"Invalid wheel filename (invalid version {version!r})"
                raise InvalidWheelFilename(msg) from e
        if "build_tag" in kwargs:
            build_tag = kwargs["build_tag"]
            # The build tag must round-trip through the filename string.
            if build_tag and (
                type(build_tag[0]) is not int
                or _parse_build_tag("".join(map(str, build_tag))) != build_tag
            ):
                msg = f"Invalid wheel filename (invalid build tag {build_tag!r})"
                raise InvalidWheelFilename(msg)
            self._build_tag = build_tag
        if "tags" in kwargs:
            tags = frozenset(kwargs["tags"])
            # Each tag must parse back to itself, so the filename round-trips.
            for tag in tags:
                try:
                    valid = parse_tag(str(tag)) == {tag}
                except InvalidTag:
                    valid = False
                if not valid:
                    msg = f"Invalid wheel filename (invalid tag {str(tag)!r})"
                    raise InvalidWheelFilename(msg)
            _compress_tags(tags)
            self._tags = tags
        if "variant" in kwargs:
            variant = kwargs["variant"]
            if variant is not None and _variant_label_regex.fullmatch(variant) is None:
                msg = f"Invalid wheel filename (invalid variant label {variant!r})"
                raise InvalidWheelFilename(msg)
            self._variant = variant

    def __replace__(self, **kwargs: Unpack[_WheelReplace]) -> Self:
        """
        __replace__(*, name=..., version=..., tags=..., build_tag=..., variant=...)

        Return a new wheel filename with parts replaced. Only the replaced
        parts are checked.

        >>> from packaging.filenames import WheelFilename
        >>> from packaging.tags import Tag
        >>> wf = WheelFilename("foo", "1.0", {Tag("py3", "none", "any")})
        >>> wf.__replace__(version="2.0").to_filename()
        'foo-2.0-py3-none-any.whl'

        :raises InvalidWheelFilename: If a replaced part is not valid.
        """
        if extra := kwargs.keys() - _WheelReplace.__optional_keys__:
            msg = f"__replace__() got unexpected keyword arguments: {sorted(extra)}"
            raise TypeError(msg)
        new = type(self).__new__(type(self))
        for attr in WheelFilename.__slots__:
            setattr(new, attr, getattr(self, attr))
        new._filename = None
        new._set(**kwargs)
        return new

    @property
    def name(self) -> NormalizedName:
        """The normalized project name."""
        return self._name

    @property
    def version(self) -> Version:
        """The parsed project version."""
        return self._version

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

        >>> from packaging.filenames import WheelFilename
        >>> from packaging.tags import Tag
        >>> wf = WheelFilename("foo", "1.0", {Tag("py3", "none", "any")})
        >>> wf.compressed_tags
        'py3-none-any'
        >>> tags = {Tag("py3", "none", "any"), Tag("py2", "none", "any")}
        >>> wf = WheelFilename("foo", "1.0", tags)
        >>> wf.compressed_tags
        'py2.py3-none-any'
        """
        return _compress_tags(self._tags)

    @property
    def build_str(self) -> str:
        """The build tag as a string, or an empty string when absent.

        >>> from packaging.filenames import WheelFilename
        >>> from packaging.tags import Tag
        >>> tags = {Tag("py3", "none", "any")}
        >>> wf = WheelFilename("foo", "1.0", tags)
        >>> wf.build_str
        ''
        >>> wf = WheelFilename("foo", "1.0", tags, build_tag=(1, "abc"))
        >>> wf.build_str
        '1abc'
        """
        return "".join(map(str, self._build_tag))

    @property
    def original_filename(self) -> str | None:
        """The filename passed to :meth:`from_filename`, or ``None``.

        This is ``None`` if the instance was constructed directly or with
        ``__replace__``.

        >>> from packaging.filenames import WheelFilename
        >>> WheelFilename.from_filename("Foo-1.0-py3-none-any.whl").original_filename
        'Foo-1.0-py3-none-any.whl'
        """
        return self._filename

    def _key(self) -> tuple[object, ...]:
        return (
            self._name,
            str(self._version),
            self._build_tag,
            self._tags,
            self._variant,
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, WheelFilename):
            return NotImplemented
        return self._key() == other._key()

    def __hash__(self) -> int:
        return hash(self._key())

    def __getstate__(self) -> str:
        return self._filename or self.to_filename()

    def __setstate__(self, state: object) -> None:
        if not isinstance(state, str):
            raise TypeError(f"Cannot restore {type(self).__name__} from {state!r}")
        other = type(self).from_filename(state)
        for attr in WheelFilename.__slots__:
            setattr(self, attr, getattr(other, attr))

    def __copy__(self) -> Self:
        return self

    def __deepcopy__(self, memo: dict[int, object]) -> Self:
        return self

    def __str__(self) -> str:
        return self.to_filename()

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}(name={self._name!r}, "
            f"version={str(self._version)!r}, "
            f"tags={self._tags!r}, "
            f"build_tag={self._build_tag!r}, "
            f"variant={self._variant!r})"
        )

    def to_filename(self) -> str:
        """
        Combines a project name, version, build tag, tag set, and variant label
        to make a properly formatted wheel filename.

        The project name is normalized such that the non-alphanumeric
        characters are replaced with ``_``. The version is normalized. The
        tag set is compressed into a wheel tag string.

        >>> from packaging.filenames import WheelFilename
        >>> from packaging.tags import Tag
        >>> tags = {Tag("py3", "none", "any")}
        >>> WheelFilename("foo-bar", "1.0", tags).to_filename()
        'foo_bar-1.0-py3-none-any.whl'
        """
        name = self._name.replace("-", "_")
        file_parts = [name, str(self._version)]
        if self._build_tag:
            file_parts.append(self.build_str)
        file_parts.append(self.compressed_tags)
        if self._variant is not None:
            file_parts.append(self._variant)
        return "-".join(file_parts) + ".whl"

    @classmethod
    def from_filename(cls, filename: str, /) -> Self:
        """
        This function takes the filename of a wheel file, and parses it into a
        :class:`WheelFilename`.

        A filename with six ``-``-separated parts has either a build tag or a
        variant label. It has a build tag if the third part starts with a digit,
        since a Python tag never does. Otherwise, the last part is a variant
        label (see :pep:`825`).

        Parsing accepts legacy names, versions, and tag orders. Call
        :meth:`validate` on the result to require a normalized filename.

        :param str filename: The name of the wheel file.
        :raises InvalidWheelFilename: If the filename in question
            does not follow the :ref:`wheel specification
            <pypug:binary-distribution-format>`.

        >>> from packaging.filenames import WheelFilename
        >>> from packaging.tags import Tag
        >>> wf = WheelFilename.from_filename("foo-1.0-py3-none-any.whl")
        >>> wf.name
        'foo'
        >>> wf.version
        <Version('1.0')>
        >>> wf.build_tag
        ()
        >>> wf.tags == {Tag("py3", "none", "any")}
        True
        """
        self = cls.__new__(cls)
        self._filename = filename
        (
            self._name,
            self._version,
            self._build_tag,
            self._tags,
            self._variant,
        ) = _parse_wheel_filename(filename)
        return self

    def validate(self) -> None:
        """
        Check that the filename this was parsed from is in its normalized form.

        The name, version, build tag, and tags must be normalized. This
        includes compressed tag set components in the sorted order required by
        :pep:`425`. An instance that was not made by :meth:`from_filename` (or
        unpickled from one) is always normalized.

        Normalization errors are collected into an
        :external:exc:`ExceptionGroup`. Each problem has its own exception
        class, such as :class:`NonNormalizedName` or
        :class:`UnsortedWheelTags`, so ``except*`` can select the checks to act
        on.

        :raises ExceptionGroup: If the filename is not normalized.

        >>> from packaging.filenames import WheelFilename
        >>> WheelFilename.from_filename("foo-1.0-py3-none-any.whl").validate()
        """
        filename = self._filename
        if filename is None:
            return
        name, version_part, build, tag_str, _ = _split_wheel_filename(filename)
        # This is a hot path, so it avoids the on_exit context manager.
        collector = _ErrorCollector()
        if _normalized_wheel_name_regex.fullmatch(name) is None:
            # A valid name that fails the fast check is not normalized.
            if _validate_regex.fullmatch(name) is None:
                inner = f"invalid project name {name!r}"
                msg = f"Invalid wheel filename ({inner}): {filename!r}"
                collector.error(InvalidProjectName(msg))
            else:
                inner = f"non-normalized project name {name!r}"
                msg = f"Invalid wheel filename ({inner}): {filename!r}"
                collector.error(NonNormalizedName(msg))
        if not _is_normalized_version(version_part, self._version):
            inner = f"non-normalized version {version_part!r}"
            msg = f"Invalid wheel filename ({inner}): {filename!r}"
            collector.error(NonNormalizedVersion(msg))
        if build is not None and build != self.build_str:
            inner = f"non-normalized build tag {build!r}"
            msg = f"Invalid wheel filename ({inner}): {filename!r}"
            collector.error(NonNormalizedBuildTag(msg))
        # The tags were parsed already. The string is the compressed form if
        # each component is lowercase, sorted, and has no duplicates.
        components = [part.split(".") for part in tag_str.split("-")]
        if any(part != sorted(part) for part in components):
            msg = (
                "Invalid wheel filename (compressed tag set components must be "
                f"in sorted order per PEP 425): {filename!r}"
            )
            collector.error(UnsortedWheelTags(msg))
        elif tag_str != tag_str.lower() or any(
            len(part) != len(set(part)) for part in components
        ):
            inner = f"non-normalized tags {tag_str!r}"
            msg = f"Invalid wheel filename ({inner}): {filename!r}"
            collector.error(NonNormalizedTags(msg))
        if collector.errors:
            collector.finalize(f"Non-normalized wheel filename: {filename!r}")


class SourceDistributionFilename:
    """Represents a source distribution filename and its parsed components.

    Instances are immutable and hashable. Two instances are equal if their
    normalized name and normalized version are equal.

    Instances are safe to serialize with :mod:`pickle`. They use a stable
    format so the same pickle can be loaded in future packaging releases.

    .. versionadded:: 26.4
    """

    __slots__ = ("_filename", "_name", "_version")
    __match_args__ = ("name", "version")

    def __init__(self, name: str, version: Version | str) -> None:
        """Create a source distribution filename from name and version.

        :param str name: The project name. It is stored in normalized form.
        :param version: The version.
        :raises InvalidSdistFilename: If the name or version is not valid.
        """
        self._filename: str | None = None
        self._set(name=name, version=version)

    def _set(self, **kwargs: Unpack[_SdistReplace]) -> None:
        if "name" in kwargs:
            name = kwargs["name"]
            try:
                self._name = canonicalize_name(name, validate=True)
            except InvalidName:
                msg = f"Invalid sdist filename (invalid project name {name!r})"
                raise InvalidSdistFilename(msg) from None
        if "version" in kwargs:
            version = kwargs["version"]
            try:
                self._version = (
                    version if isinstance(version, Version) else Version(version)
                )
            except InvalidVersion as e:
                msg = f"Invalid sdist filename (invalid version {version!r})"
                raise InvalidSdistFilename(msg) from e

    def __replace__(self, **kwargs: Unpack[_SdistReplace]) -> Self:
        """
        __replace__(*, name=..., version=...)

        Return a new sdist filename with parts replaced. Only the replaced
        parts are checked.

        >>> from packaging.filenames import SourceDistributionFilename
        >>> fn = SourceDistributionFilename("foo", "1.0")
        >>> fn.__replace__(version="2.0").to_filename()
        'foo-2.0.tar.gz'

        :raises InvalidSdistFilename: If a replaced part is not valid.
        """
        if extra := kwargs.keys() - _SdistReplace.__optional_keys__:
            msg = f"__replace__() got unexpected keyword arguments: {sorted(extra)}"
            raise TypeError(msg)
        new = type(self).__new__(type(self))
        for attr in SourceDistributionFilename.__slots__:
            setattr(new, attr, getattr(self, attr))
        new._filename = None
        new._set(**kwargs)
        return new

    @property
    def name(self) -> NormalizedName:
        """The normalized project name."""
        return self._name

    @property
    def version(self) -> Version:
        """The parsed project version."""
        return self._version

    @property
    def original_filename(self) -> str | None:
        """The filename passed to :meth:`from_filename`, or ``None``.

        This is ``None`` if the instance was constructed directly or with
        ``__replace__``.

        >>> from packaging.filenames import SourceDistributionFilename
        >>> SourceDistributionFilename.from_filename("Foo-1.0.zip").original_filename
        'Foo-1.0.zip'
        """
        return self._filename

    def _key(self) -> tuple[object, ...]:
        return (self._name, str(self._version))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SourceDistributionFilename):
            return NotImplemented
        return self._key() == other._key()

    def __hash__(self) -> int:
        return hash(self._key())

    def __getstate__(self) -> str:
        return self._filename or self.to_filename()

    def __setstate__(self, state: object) -> None:
        if not isinstance(state, str):
            raise TypeError(f"Cannot restore {type(self).__name__} from {state!r}")
        other = type(self).from_filename(state)
        for attr in SourceDistributionFilename.__slots__:
            setattr(self, attr, getattr(other, attr))

    def __copy__(self) -> Self:
        return self

    def __deepcopy__(self, memo: dict[int, object]) -> Self:
        return self

    def __str__(self) -> str:
        return self.to_filename()

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}(name={self._name!r}, "
            f"version={str(self._version)!r})"
        )

    def to_filename(self) -> str:
        """
        Combines the project name and a version to make a valid sdist filename. The
        project name is normalized as required so that any run of ``-._``
        characters are replaced with ``_`` and characters are lower cased. The
        version is normalized.

        >>> from packaging.filenames import SourceDistributionFilename
        >>> SourceDistributionFilename("foo-bar", "1.0").to_filename()
        'foo_bar-1.0.tar.gz'
        """
        name = self._name.replace("-", "_")
        return f"{name}-{self._version}.tar.gz"

    @classmethod
    def from_filename(cls, filename: str, /) -> Self:
        """
        This function takes the filename of a sdist file (as specified
        in the `Source distribution format`_ documentation), and parses
        it into a :class:`SourceDistributionFilename`.

        Parsing accepts legacy names, versions, and the ``.zip`` extension. Call
        :meth:`validate` on the result to require a normalized filename.

        :param str filename: The name of the sdist file.
        :raises InvalidSdistFilename: If the filename does not end
            with an sdist extension (``.zip`` or ``.tar.gz``), if it does not
            contain a dash separating the name and the version of the distribution,
            if the project name is empty, or if the version portion is not a valid
            version.

        >>> from packaging.filenames import SourceDistributionFilename
        >>> fn = SourceDistributionFilename.from_filename("foo-1.0.tar.gz")
        >>> fn.name
        'foo'
        >>> fn.version
        <Version('1.0')>

        .. _Source distribution format: https://packaging.python.org/specifications/source-distribution-format/#source-distribution-file-name
        """
        self = cls.__new__(cls)
        self._filename = filename
        self._name, self._version = _parse_sdist_filename(filename)
        return self

    def validate(self) -> None:
        """
        Check that the filename this was parsed from is in its normalized form.

        The extension must be ``.tar.gz``, and the name and version must be
        normalized. An instance that was not made by :meth:`from_filename` (or
        unpickled from one) is always normalized.

        Normalization errors are collected into an
        :external:exc:`ExceptionGroup`. Each problem has its own exception
        class, such as :class:`NonNormalizedName`, so ``except*`` can select
        the checks to act on.

        :raises ExceptionGroup: If the filename is not normalized.

        >>> from packaging.filenames import SourceDistributionFilename
        >>> SourceDistributionFilename.from_filename("foo-1.0.tar.gz").validate()
        """
        filename = self._filename
        if filename is None:
            return
        ext = ".tar.gz" if filename.endswith(".tar.gz") else ".zip"
        stem = filename[: -len(ext)]
        name_part, _, version_part = stem.rpartition("-")
        # This is a hot path, so it avoids the on_exit context manager.
        collector = _ErrorCollector()
        if ext != ".tar.gz":
            msg = f"Invalid sdist filename (extension must be '.tar.gz'): {filename!r}"
            collector.error(InvalidSdistFilename(msg))
        if _normalized_wheel_name_regex.fullmatch(name_part) is None:
            # A valid name that fails the fast check is not normalized.
            if _validate_regex.fullmatch(name_part) is None:
                inner = f"invalid project name {name_part!r}"
                msg = f"Invalid sdist filename ({inner}): {filename!r}"
                collector.error(InvalidProjectName(msg))
            else:
                inner = f"non-normalized project name {name_part!r}"
                msg = f"Invalid sdist filename ({inner}): {filename!r}"
                collector.error(NonNormalizedName(msg))
        if not _is_normalized_version(version_part, self._version):
            inner = f"non-normalized version {version_part!r}"
            msg = f"Invalid sdist filename ({inner}): {filename!r}"
            collector.error(NonNormalizedVersion(msg))
        if collector.errors:
            collector.finalize(f"Non-normalized sdist filename: {filename!r}")
