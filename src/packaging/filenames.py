# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.

from __future__ import annotations

import copy
import re
from typing import TYPE_CHECKING, TypedDict

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
    from collections.abc import Iterable, Mapping

    from typing_extensions import Self, Unpack

    from .utils import NormalizedName

__all__ = [
    "BuildTag",
    "InvalidFilename",
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


# PEP 427: The build number must start with a digit.
_build_tag_regex = re.compile(r"(\d+)(.*)", re.ASCII)
# A build tag suffix must not start with a digit, so the number is unambiguous.
_build_suffix_regex = re.compile(r"(?:[a-z_.][a-z0-9_.]*)?", re.ASCII | re.IGNORECASE)
_variant_label_regex = re.compile(r"[0-9a-z._]{1,16}", re.ASCII)
# PEP 427: Valid characters for an escaped project name in a wheel filename.
# Requires at least one character so an empty project name is rejected.
_wheel_name_regex = re.compile(r"[\w.]+")


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


def _check_replace_keys(kwargs: Mapping[str, object], allowed: frozenset[str]) -> None:
    if extra := kwargs.keys() - allowed:
        msg = f"__replace__() got unexpected keyword arguments: {sorted(extra)}"
        raise TypeError(msg)


def _invalid(
    error: type[InvalidFilename],
    inner: str,
    filename: str | None = None,
    *,
    wheel: bool | None = None,
) -> InvalidFilename:
    if wheel is None:
        wheel = issubclass(error, InvalidWheelFilename)
    kind = "wheel" if wheel else "sdist"
    msg = f"Invalid {kind} filename ({inner})"
    if filename is not None:
        msg = f"{msg}: {filename!r}"
    return error(msg)


def _check_name(error: type[InvalidFilename], name: str) -> NormalizedName:
    try:
        return canonicalize_name(name, validate=True)
    except InvalidName:
        raise _invalid(error, f"invalid project name {name!r}") from None


def _parse_version(
    error: type[InvalidFilename], version: Version | str, filename: str | None = None
) -> Version:
    if isinstance(version, Version):
        return version
    try:
        return Version(version)
    except InvalidVersion as e:
        raise _invalid(error, f"invalid version {version!r}", filename) from e


def _check_normalized(
    collector: _ErrorCollector,
    error: type[InvalidFilename],
    name: str,
    version_part: str,
    version: Version,
    filename: str,
) -> None:
    """Collect errors if the name and version parts are not normalized.

    An invalid name is raised directly.
    """
    wheel = issubclass(error, InvalidWheelFilename)
    try:
        cname = canonicalize_name(name, validate=True).replace("-", "_")
    except InvalidName:
        raise _invalid(error, f"invalid project name {name!r}", filename) from None
    if name != cname:
        inner = f"non-normalized project name {name!r}"
        collector.error(_invalid(NonNormalizedName, inner, filename, wheel=wheel))
    if version_part != str(version):
        inner = f"non-normalized version {version_part!r}"
        collector.error(_invalid(NonNormalizedVersion, inner, filename, wheel=wheel))


def _check_build_tag(build_tag: BuildTag) -> None:
    if build_tag and (
        build_tag[0] < 0 or _build_suffix_regex.fullmatch(build_tag[1]) is None
    ):
        raise _invalid(InvalidWheelFilename, f"invalid build tag {build_tag!r}")


def _check_variant(variant: str | None, filename: str | None = None) -> None:
    if variant is not None and _variant_label_regex.fullmatch(variant) is None:
        inner = f"invalid variant label {variant!r}"
        raise _invalid(InvalidWheelFilename, inner, filename)


class WheelFilename:
    """Represents a wheel filename and its parsed components.

    Instances are immutable and hashable. Two instances are equal if their
    normalized name, normalized version, build tag, tags, and variant are equal.

    .. versionadded:: 26.4
    """

    __slots__ = ("_build_tag", "_name", "_tags", "_variant", "_version")
    __match_args__ = ("name", "version", "build_tag", "tags", "variant")

    def __init__(
        self,
        name: str,
        version: Version | str,
        build_tag: BuildTag = (),
        tags: Iterable[Tag] = (),
        variant: str | None = None,
    ) -> None:
        """Create a wheel filename from its component parts.

        :param name: The project name. It is stored in normalized form.
        :param version: The version.
        :param build_tag: Optional wheel build tag.
        :param tags: The wheel tag set. It must not be empty to make a filename.
        :param variant: The variant label (see :pep:`825`), or ``None``.
        :raises InvalidWheelFilename: If the name, version, build tag, or
            variant label is not valid.
        """
        _check_build_tag(build_tag)
        _check_variant(variant)
        self._name = _check_name(InvalidWheelFilename, name)
        self._version = _parse_version(InvalidWheelFilename, version)
        self._build_tag = build_tag
        self._tags = frozenset(tags)
        self._variant = variant

    def __replace__(self, **kwargs: Unpack[_WheelReplace]) -> Self:
        """
        __replace__(*, name=..., version=..., build_tag=..., tags=..., variant=...)

        Return a new wheel filename with parts replaced. Only the replaced
        parts are checked.

        >>> from packaging.filenames import WheelFilename
        >>> from packaging.tags import Tag
        >>> wf = WheelFilename("foo", "1.0", tags={Tag("py3", "none", "any")})
        >>> wf.__replace__(version="2.0").to_filename()
        'foo-2.0-py3-none-any.whl'

        :raises InvalidWheelFilename: If a replaced part is not valid.
        """
        _check_replace_keys(kwargs, _WheelReplace.__optional_keys__)
        new = copy.copy(self)
        if "name" in kwargs:
            new._name = _check_name(InvalidWheelFilename, kwargs["name"])
        if "version" in kwargs:
            new._version = _parse_version(InvalidWheelFilename, kwargs["version"])
        if "build_tag" in kwargs:
            _check_build_tag(kwargs["build_tag"])
            new._build_tag = kwargs["build_tag"]
        if "tags" in kwargs:
            new._tags = frozenset(kwargs["tags"])
        if "variant" in kwargs:
            _check_variant(kwargs["variant"])
            new._variant = kwargs["variant"]
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
        tags = self._tags
        if not tags:
            inner = "the tag set must have at least one tag"
            raise _invalid(InvalidWheelFilename, inner)
        interpreters = sorted({tag.interpreter for tag in tags})
        abis = sorted({tag.abi for tag in tags})
        platforms = sorted({tag.platform for tag in tags})
        # A compressed tag string always expands to every combination of its fields.
        if len(tags) != len(interpreters) * len(abis) * len(platforms):
            inner = (
                "the tag set cannot be compressed, it must contain every combination"
            )
            msg = f"Invalid wheel filename ({inner}): {sorted(map(str, tags))!r}"
            raise InvalidWheelFilename(msg)
        return "-".join((".".join(interpreters), ".".join(abis), ".".join(platforms)))

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

    def __str__(self) -> str:
        return self.to_filename()

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}(name={self._name!r}, "
            f"version={str(self._version)!r}, "
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

        :raises InvalidWheelFilename: If the tag set cannot be compressed (see
            :attr:`compressed_tags`).

        >>> from packaging.filenames import WheelFilename
        >>> from packaging.tags import Tag
        >>> tags = {Tag("py3", "none", "any")}
        >>> WheelFilename("foo-bar", "1.0", (), tags).to_filename()
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
        name, version_part, build_part, tag_str, variant = _split_wheel_filename(
            filename
        )

        try:
            tags = parse_tag(tag_str)
        except InvalidTag:
            raise _invalid(
                InvalidWheelFilename, f"invalid tag component {tag_str!r}", filename
            ) from None

        # See PEP 427 for the rules on escaping the project name.
        if "__" in name or _wheel_name_regex.fullmatch(name) is None:
            raise _invalid(
                InvalidWheelFilename, f"invalid project name {name!r}", filename
            )

        version = _parse_version(InvalidWheelFilename, version_part, filename)

        build_match = _build_tag_regex.match(build_part or "")
        build_tag: BuildTag = (
            (int(build_match[1]), build_match[2]) if build_match else ()
        )

        _check_variant(variant, filename)

        # Parsing accepts legacy names, so skip the constructor checks.
        self = cls.__new__(cls)
        self._name = canonicalize_name(name)
        self._version = version
        self._build_tag = build_tag
        self._tags = tags
        self._variant = variant
        return self


def _split_wheel_filename(
    filename: str,
) -> tuple[str, str, str | None, str, str | None]:
    """Split a wheel filename into name, version, build, tag, and variant parts."""
    if not filename.endswith(".whl"):
        raise _invalid(InvalidWheelFilename, "extension must be '.whl'", filename)

    parts = filename[:-4].split("-")
    if len(parts) not in {5, 6, 7}:
        raise _invalid(InvalidWheelFilename, "wrong number of parts", filename)

    name, version_part, *rest = parts

    # Six parts are ambiguous: a build tag or a variant label (PEP 825).
    # A build tag starts with a digit, and a Python tag never does.
    has_build = len(rest) > 3 and _build_tag_regex.match(rest[0]) is not None
    if len(rest) == 5 and not has_build:
        raise _invalid(
            InvalidWheelFilename, f"invalid build number {rest[0]!r}", filename
        )
    build_part = rest.pop(0) if has_build else None
    variant = rest.pop() if len(rest) == 4 else None
    return name, version_part, build_part, "-".join(rest), variant


def _check_ordered_tags(filename: str, tag_str: str) -> None:
    try:
        parse_tag(tag_str, validate_order=True)
    except UnsortedTagsError:
        inner = "compressed tag set components must be in sorted order per PEP 425"
        raise _invalid(UnsortedWheelTags, inner, filename) from None


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
    wf = WheelFilename.from_filename(filename)
    with _ErrorCollector().on_exit(
        f"Non-normalized wheel filename: {filename!r}"
    ) as collector:
        name, version_part, build_part, tag_str, _ = _split_wheel_filename(filename)

        _check_normalized(
            collector, InvalidWheelFilename, name, version_part, wf.version, filename
        )
        if build_part is not None and build_part != wf.build_str:
            inner = f"non-normalized build tag {build_part!r}"
            collector.error(_invalid(NonNormalizedBuildTag, inner, filename))
        try:
            _check_ordered_tags(filename, tag_str)
        except UnsortedWheelTags as e:
            collector.error(e)
        else:
            if wf.compressed_tags != tag_str:
                inner = f"non-normalized tags {tag_str!r}"
                collector.error(_invalid(NonNormalizedTags, inner, filename))


class SourceDistributionFilename:
    """Represents a source distribution filename and its parsed components.

    Instances are immutable and hashable. Two instances are equal if their
    normalized name and normalized version are equal.

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
        self._name = _check_name(InvalidSdistFilename, name)
        self._version = _parse_version(InvalidSdistFilename, version)

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
        _check_replace_keys(kwargs, _SdistReplace.__optional_keys__)
        new = copy.copy(self)
        if "name" in kwargs:
            new._name = _check_name(InvalidSdistFilename, kwargs["name"])
        if "version" in kwargs:
            new._version = _parse_version(InvalidSdistFilename, kwargs["version"])
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
        name_part, version_part = _split_sdist_filename(filename)
        version = _parse_version(InvalidSdistFilename, version_part, filename)

        # Parsing accepts legacy names, so skip the constructor checks.
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
        raise _invalid(InvalidSdistFilename, inner, filename)

    # PEP 625: Source distributions may only have one hyphen, separating
    # the name and version. Validation rejects extra hyphens via the
    # normalized name check.
    name_part, sep, version_part = file_stem.rpartition("-")
    if not sep:
        inner = "hyphen must separate name and version parts"
        raise _invalid(InvalidSdistFilename, inner, filename)
    if not name_part:
        raise _invalid(InvalidSdistFilename, "empty project name", filename)
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
        raise _invalid(InvalidSdistFilename, "extension must be '.tar.gz'", filename)
    fn = SourceDistributionFilename.from_filename(filename)
    with _ErrorCollector().on_exit(
        f"Non-normalized sdist filename: {filename!r}"
    ) as collector:
        name_part, version_part = _split_sdist_filename(filename)
        _check_normalized(
            collector,
            InvalidSdistFilename,
            name_part,
            version_part,
            fn.version,
            filename,
        )
