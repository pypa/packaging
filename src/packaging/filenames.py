# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.

from __future__ import annotations

import re
from typing import TYPE_CHECKING, NamedTuple, TypedDict

from .errors import _ErrorCollector
from .tags import InvalidTag, Tag, UnsortedTagsError, parse_tag
from .utils import (
    BuildTag,
    InvalidFilename,
    InvalidName,
    InvalidSdistFilename,
    InvalidWheelFilename,
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
    "validate_sdist_filename",
    "validate_wheel_filename",
]


def __dir__() -> list[str]:
    return __all__


# PEP 427: The build number must start with a digit. The suffix must not, so
# the number is unambiguous.
_build_tag_regex = re.compile(r"(\d+)([a-z_.][a-z0-9_.]*)?", re.ASCII | re.IGNORECASE)
_variant_label_regex = re.compile(r"[0-9a-z._]{1,16}", re.ASCII)
# PEP 427: Valid characters for an escaped project name in a wheel filename.
# Requires at least one character so an empty project name is rejected.
_wheel_name_regex = re.compile(r"[\w.]+")


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


class UnsortedWheelTags(InvalidWheelFilename):
    """
    The compressed tag set components in a wheel filename are not in the
    sorted order required by :pep:`425`.

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


def _parse_build_tag(build: str) -> BuildTag:
    """Parse a build tag string, returning an empty tuple if it is not valid."""
    build_match = _build_tag_regex.fullmatch(build)
    if build_match is None:
        return ()
    return (int(build_match[1]), build_match[2] or "")


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

    __slots__ = ("_build_tag", "_name", "_tags", "_variant", "_version")
    __match_args__ = ("name", "version", "tags", "build_tag", "variant")

    def __init__(
        self,
        name: str,
        version: Version | str,
        tags: Iterable[Tag],
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
        return self.to_filename()

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

        Parsing accepts legacy names, versions, and tag orders. Use
        :func:`validate_wheel_filename` first to require a normalized filename.

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
        return cls._from_parts(filename, _split_wheel_filename(filename))

    @classmethod
    def _from_parts(
        cls, filename: str, parts: _WheelParts, *, validate_order: bool = False
    ) -> Self:
        """Build from split parts, accepting legacy names and versions."""
        tags = _parse_tags(filename, parts.tags, validate_order=validate_order)

        # See PEP 427 for the rules on escaping the project name.
        if "__" in parts.name or _wheel_name_regex.fullmatch(parts.name) is None:
            inner = f"invalid project name {parts.name!r}"
            msg = f"Invalid wheel filename ({inner}): {filename!r}"
            raise InvalidWheelFilename(msg)

        try:
            version = Version(parts.version)
        except InvalidVersion as e:
            inner = f"invalid version {parts.version!r}"
            msg = f"Invalid wheel filename ({inner}): {filename!r}"
            raise InvalidWheelFilename(msg) from e

        if (
            parts.variant is not None
            and _variant_label_regex.fullmatch(parts.variant) is None
        ):
            inner = f"invalid variant label {parts.variant!r}"
            msg = f"Invalid wheel filename ({inner}): {filename!r}"
            raise InvalidWheelFilename(msg)

        build_tag: BuildTag = ()
        if parts.build is not None:
            build_tag = _parse_build_tag(parts.build)
            if not build_tag:
                inner = f"invalid build tag {parts.build!r}"
                msg = f"Invalid wheel filename ({inner}): {filename!r}"
                raise InvalidWheelFilename(msg)

        self = cls.__new__(cls)
        self._name = canonicalize_name(parts.name)
        self._version = version
        self._build_tag = build_tag
        self._tags = tags
        self._variant = parts.variant
        return self


class _WheelParts(NamedTuple):
    name: str
    version: str
    build: str | None
    tags: str
    variant: str | None


def _split_wheel_filename(filename: str, *, variants: bool = True) -> _WheelParts:
    """Split a wheel filename into its raw parts.

    With ``variants`` false, a seventh part or a sixth part that is not a
    build number is rejected.
    """
    if not filename.endswith(".whl"):
        msg = f"Invalid wheel filename (extension must be '.whl'): {filename!r}"
        raise InvalidWheelFilename(msg)

    parts = filename[:-4].split("-")
    if len(parts) not in {5, 6, 7}:
        msg = f"Invalid wheel filename (wrong number of parts): {filename!r}"
        raise InvalidWheelFilename(msg)
    if len(parts) == 7 and not variants:
        msg = (
            "Invalid wheel filename (variant wheels are not supported, "
            f"use packaging.filenames.WheelFilename instead for support): {filename!r}"
        )
        raise InvalidWheelFilename(msg)

    name, version_part, *rest = parts

    # Six parts are ambiguous: a build tag or a variant label (PEP 825).
    # A build tag starts with a digit, and a Python tag never does.
    has_build = len(rest) > 3 and rest[0][:1].isdigit()
    if len(rest) == 5 and not has_build:
        msg = f"Invalid wheel filename (invalid build number {rest[0]!r}): {filename!r}"
        raise InvalidWheelFilename(msg)
    if len(rest) == 4 and not has_build and not variants:
        msg = (
            "Invalid wheel filename (invalid build number or unsupported "
            f"variant label): {filename!r}"
        )
        raise InvalidWheelFilename(msg)
    build_part = rest.pop(0) if has_build else None
    variant = rest.pop() if len(rest) == 4 else None
    return _WheelParts(name, version_part, build_part, "-".join(rest), variant)


def _parse_tags(filename: str, tag_str: str, *, validate_order: bool) -> frozenset[Tag]:
    try:
        return parse_tag(tag_str, validate_order=validate_order)
    except UnsortedTagsError:
        msg = (
            "Invalid wheel filename (compressed tag set components must be in "
            f"sorted order per PEP 425): {filename!r}"
        )
        raise UnsortedWheelTags(msg) from None
    except InvalidTag:
        inner = f"invalid tag component {tag_str!r}"
        msg = f"Invalid wheel filename ({inner}): {filename!r}"
        raise InvalidWheelFilename(msg) from None


def validate_wheel_filename(filename: str, /) -> None:
    """
    Check that a wheel filename is valid and in its normalized form.

    The name, version, build tag, and tags must be normalized. This includes
    compressed tag set components in the sorted order required by :pep:`425`.

    Normalization errors are collected into an :external:exc:`ExceptionGroup`.
    Each problem has its own exception class, such as :class:`NonNormalizedName`
    or :class:`UnsortedWheelTags`, so ``except*`` can select the checks to act
    on.

    :param str filename: The name of the wheel file.
    :raises InvalidWheelFilename: If the filename is not valid.
    :raises ExceptionGroup: If the filename is not normalized.

    >>> from packaging.filenames import validate_wheel_filename
    >>> validate_wheel_filename("foo-1.0-py3-none-any.whl")

    .. versionadded:: 26.4
    """
    parts = _split_wheel_filename(filename)
    wf = WheelFilename._from_parts(filename, parts)
    with _ErrorCollector().on_exit(
        f"Non-normalized wheel filename: {filename!r}"
    ) as collector:
        try:
            normalized = canonicalize_name(parts.name, validate=True)
        except InvalidName:
            inner = f"invalid project name {parts.name!r}"
            msg = f"Invalid wheel filename ({inner}): {filename!r}"
            collector.error(InvalidProjectName(msg))
        else:
            if parts.name != normalized.replace("-", "_"):
                inner = f"non-normalized project name {parts.name!r}"
                msg = f"Invalid wheel filename ({inner}): {filename!r}"
                collector.error(NonNormalizedName(msg))
        if parts.version != str(wf.version):
            inner = f"non-normalized version {parts.version!r}"
            msg = f"Invalid wheel filename ({inner}): {filename!r}"
            collector.error(NonNormalizedVersion(msg))
        if parts.build is not None and parts.build != wf.build_str:
            inner = f"non-normalized build tag {parts.build!r}"
            msg = f"Invalid wheel filename ({inner}): {filename!r}"
            collector.error(NonNormalizedBuildTag(msg))
        # The tags were parsed already, so only the order needs a check here.
        components = [part.split(".") for part in parts.tags.split("-")]
        if any(part != sorted(part) for part in components):
            msg = (
                "Invalid wheel filename (compressed tag set components must be "
                f"in sorted order per PEP 425): {filename!r}"
            )
            collector.error(UnsortedWheelTags(msg))
        elif wf.compressed_tags != parts.tags:
            inner = f"non-normalized tags {parts.tags!r}"
            msg = f"Invalid wheel filename ({inner}): {filename!r}"
            collector.error(NonNormalizedTags(msg))


class SourceDistributionFilename:
    """Represents a source distribution filename and its parsed components.

    Instances are immutable and hashable. Two instances are equal if their
    normalized name and normalized version are equal.

    Instances are safe to serialize with :mod:`pickle`. They use a stable
    format so the same pickle can be loaded in future packaging releases.

    .. versionadded:: 26.4
    """

    __slots__ = ("_name", "_version")
    __match_args__ = ("name", "version")

    def __init__(self, name: str, version: Version | str) -> None:
        """Create a source distribution filename from name and version.

        :param str name: The project name. It is stored in normalized form.
        :param version: The version.
        :raises InvalidSdistFilename: If the name or version is not valid.
        """
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

    def _key(self) -> tuple[object, ...]:
        return (self._name, str(self._version))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SourceDistributionFilename):
            return NotImplemented
        return self._key() == other._key()

    def __hash__(self) -> int:
        return hash(self._key())

    def __getstate__(self) -> str:
        return self.to_filename()

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

        Parsing accepts legacy names, versions, and the ``.zip`` extension. Use
        :func:`validate_sdist_filename` first to require a normalized filename.

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
        return cls._from_parts(filename, *_split_sdist_filename(filename))

    @classmethod
    def _from_parts(cls, filename: str, name_part: str, version_part: str) -> Self:
        """Build from split parts, accepting legacy names and versions."""
        try:
            version = Version(version_part)
        except InvalidVersion as e:
            inner = f"invalid version {version_part!r}"
            msg = f"Invalid sdist filename ({inner}): {filename!r}"
            raise InvalidSdistFilename(msg) from e
        self = cls.__new__(cls)
        self._name = canonicalize_name(name_part)
        self._version = version
        return self


def _split_sdist_filename(filename: str) -> tuple[str, str]:
    """Split a sdist filename into name and version parts."""
    # PEP 625: Source distributions must end with .tar.gz. Parsing also
    # accepts .zip for backward compatibility.
    if filename.endswith(".tar.gz"):
        file_stem = filename[: -len(".tar.gz")]
    elif filename.endswith(".zip"):
        file_stem = filename[: -len(".zip")]
    else:
        inner = "extension must be '.tar.gz' or '.zip'"
        msg = f"Invalid sdist filename ({inner}): {filename!r}"
        raise InvalidSdistFilename(msg)

    # PEP 625: Source distributions may only have one hyphen, separating
    # the name and version. Validation rejects extra hyphens via the
    # normalized name check.
    name_part, sep, version_part = file_stem.rpartition("-")
    if not sep:
        inner = "hyphen must separate name and version parts"
        msg = f"Invalid sdist filename ({inner}): {filename!r}"
        raise InvalidSdistFilename(msg)
    if not name_part:
        msg = f"Invalid sdist filename (empty project name): {filename!r}"
        raise InvalidSdistFilename(msg)
    return name_part, version_part


def validate_sdist_filename(filename: str, /) -> None:
    """
    Check that a sdist filename is valid and in its normalized form.

    The extension must be ``.tar.gz``, and the name and version must be
    normalized.

    Normalization errors are collected into an :external:exc:`ExceptionGroup`.
    Each problem has its own exception class, such as :class:`NonNormalizedName`,
    so ``except*`` can select the checks to act on.

    :param str filename: The name of the sdist file.
    :raises InvalidSdistFilename: If the filename is not valid, or if the
        extension is not ``.tar.gz``.
    :raises ExceptionGroup: If the filename is not normalized.

    >>> from packaging.filenames import validate_sdist_filename
    >>> validate_sdist_filename("foo-1.0.tar.gz")

    .. versionadded:: 26.4
    """
    if not filename.endswith(".tar.gz"):
        msg = f"Invalid sdist filename (extension must be '.tar.gz'): {filename!r}"
        raise InvalidSdistFilename(msg)
    name_part, version_part = _split_sdist_filename(filename)
    fn = SourceDistributionFilename._from_parts(filename, name_part, version_part)
    with _ErrorCollector().on_exit(
        f"Non-normalized sdist filename: {filename!r}"
    ) as collector:
        try:
            normalized = canonicalize_name(name_part, validate=True)
        except InvalidName:
            inner = f"invalid project name {name_part!r}"
            msg = f"Invalid sdist filename ({inner}): {filename!r}"
            collector.error(InvalidProjectName(msg))
        else:
            if name_part != normalized.replace("-", "_"):
                inner = f"non-normalized project name {name_part!r}"
                msg = f"Invalid sdist filename ({inner}): {filename!r}"
                collector.error(NonNormalizedName(msg))
        if version_part != str(fn.version):
            inner = f"non-normalized version {version_part!r}"
            msg = f"Invalid sdist filename ({inner}): {filename!r}"
            collector.error(NonNormalizedVersion(msg))
