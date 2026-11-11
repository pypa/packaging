# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

from .errors import _ErrorCollector
from .utils import (
    _ISSUE_BUILD,
    _ISSUE_NAME,
    _ISSUE_TAGS,
    BuildTag,
    InvalidFilename,
    InvalidName,
    InvalidSdistFilename,
    InvalidWheelFilename,
    UnsortedWheelTags,
    _normalized_release_regex,
    _normalized_wheel_name_regex,
    _parse_wheel_parts,
    _split_sdist_filename,
    _split_wheel_filename,
    _validate_regex,
    canonicalize_name,
    parse_sdist_filename,
)
from .version import InvalidVersion, Version

if TYPE_CHECKING:
    from collections.abc import Iterable

    from typing_extensions import Self, Unpack

    from .tags import Tag
    from .utils import NormalizedName, _WheelParts

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
    "NormalizedSdistFilename",
    "NormalizedWheelFilename",
    "SourceDistributionFilename",
    "UnsortedWheelTags",
    "WheelFilename",
    "ZipSdistFilename",
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


class ZipSdistFilename(InvalidSdistFilename):
    """
    The sdist filename uses the legacy ``.zip`` extension, not ``.tar.gz``.

    .. versionadded:: 26.4
    """


class _RawSdistChanges(TypedDict, total=False):
    name: str
    version: str
    extension: str


class _RawWheelChanges(TypedDict, total=False):
    name: str
    version: str
    tags: str
    build_tag: str | None
    variant: str | None


class _SdistChanges(TypedDict, total=False):
    name: str
    version: Version


class _WheelChanges(TypedDict, total=False):
    name: str
    version: Version
    tags: Iterable[Tag]
    build_tag: BuildTag
    variant: str | None


def _is_normalized_version(version_part: str, version: Version) -> bool:
    # str(version) is slow, so check the common case first.
    return _normalized_release_regex.fullmatch(
        version_part
    ) is not None or version_part == str(version)


def _state(cls: type, state: object) -> str:
    if not isinstance(state, str):
        raise TypeError(f"Cannot restore {cls.__name__} from {state!r}")
    return state


class WheelFilename:
    """A wheel filename, split into its parts as they are written.

    Only the structure of the filename is checked. Call :meth:`normalize` to
    check the parts and get a :class:`NormalizedWheelFilename`.

    Instances are immutable and hashable. Two instances are equal if their
    filenames are equal.

    Instances are safe to serialize with :mod:`pickle`. They use a stable
    format so the same pickle can be loaded in future packaging releases.

    .. versionadded:: 26.4
    """

    __slots__ = ("_filename", "_parts")
    __match_args__ = ("name", "version", "tags")

    def __init__(
        self,
        name: str,
        version: str,
        tags: str,
        *,
        build_tag: str | None = None,
        variant: str | None = None,
    ) -> None:
        """Create a wheel filename from its parts, as they are written.

        :param name: The project name.
        :param version: The version.
        :param tags: The compressed tag string, like ``"py2.py3-none-any"``.
        :param build_tag: The build tag, like ``"1abc"``, or ``None``.
        :param variant: The variant label (see :pep:`825`), or ``None``.
        :raises InvalidWheelFilename: If the parts do not make a filename that
            splits into the same parts.
        """
        parts = (name, version, build_tag, tags, variant)
        filename = "-".join([part for part in parts if part is not None]) + ".whl"
        if _split_wheel_filename(filename) != parts:
            msg = (
                "Invalid wheel filename (the filename does not split into the "
                f"given parts): {filename!r}"
            )
            raise InvalidWheelFilename(msg)
        self._filename = filename
        self._parts: _WheelParts = parts

    @classmethod
    def from_filename(cls, filename: str, /) -> Self:
        """
        Split the filename of a wheel file into its parts.

        A filename with six ``-``-separated parts has either a build tag or a
        variant label. It has a build tag if the third part starts with a digit,
        since a Python tag never does. Otherwise, the last part is a variant
        label (see :pep:`825`).

        The parts are not checked. Call :meth:`normalize` to check them.

        :param str filename: The name of the wheel file.
        :raises InvalidWheelFilename: If the filename does not have the
            ``.whl`` extension or the correct number of parts.

        >>> from packaging.filenames import WheelFilename
        >>> wf = WheelFilename.from_filename("Foo-1.0-py3-none-any.whl")
        >>> wf.name
        'Foo'
        >>> wf.version
        '1.0'
        >>> wf.tags
        'py3-none-any'
        """
        self = cls.__new__(cls)
        self._filename = filename
        self._parts = _split_wheel_filename(filename)
        return self

    def __replace__(self, **changes: Unpack[_RawWheelChanges]) -> Self:
        """
        __replace__(*, name=..., version=..., tags=..., build_tag=..., variant=...)

        Return a new wheel filename with parts replaced. The other parts are
        kept as written.

        >>> from packaging.filenames import WheelFilename
        >>> wf = WheelFilename.from_filename("Foo.Bar-1.0-py3-none-any.whl")
        >>> wf.__replace__(tags="py2.py3-none-any").to_filename()
        'Foo.Bar-1.0-py2.py3-none-any.whl'

        :raises InvalidWheelFilename: If the new parts do not make a filename
            that splits into the same parts.
        """
        name, version, build_tag, tags, variant = self._parts
        parts: _RawWheelChanges = {
            "name": name,
            "version": version,
            "tags": tags,
            "build_tag": build_tag,
            "variant": variant,
        }
        parts.update(changes)
        return type(self)(**parts)

    @property
    def name(self) -> str:
        """The project name, as written.

        Use this with :attr:`version` to find the ``.dist-info`` directory.
        """
        return self._parts[0]

    @property
    def version(self) -> str:
        """The version, as written."""
        return self._parts[1]

    @property
    def build_tag(self) -> str | None:
        """The build tag, as written, or ``None`` when absent."""
        return self._parts[2]

    @property
    def tags(self) -> str:
        """The compressed tag string, as written."""
        return self._parts[3]

    @property
    def variant(self) -> str | None:
        """The variant label (see :pep:`825`), or ``None``."""
        return self._parts[4]

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, WheelFilename):
            return NotImplemented
        return self._filename == other._filename

    def __hash__(self) -> int:
        return hash(self._filename)

    def __getstate__(self) -> str:
        return self._filename

    def __setstate__(self, state: object) -> None:
        self._filename = _state(type(self), state)
        self._parts = _split_wheel_filename(self._filename)

    def __str__(self) -> str:
        return self._filename

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}({self._filename!r})>"

    def to_filename(self) -> str:
        """The filename, as written.

        >>> from packaging.filenames import WheelFilename
        >>> WheelFilename("Foo", "01.0", "py3-none-any").to_filename()
        'Foo-01.0-py3-none-any.whl'
        """
        return self._filename

    def normalize(self, *, strict: bool = False) -> NormalizedWheelFilename:
        """
        Parse the parts into a :class:`NormalizedWheelFilename`.

        Parsing accepts legacy names, versions, and tag orders. With
        **strict**, the filename must also be in its normalized form: the name,
        version, build tag, and tags must be normalized. This includes
        compressed tag set components in the sorted order required by
        :pep:`425`.

        Normalization errors are collected into an
        :external:exc:`ExceptionGroup`. Each problem has its own exception
        class, such as :class:`NonNormalizedName` or
        :class:`UnsortedWheelTags`, so ``except*`` can select the checks to act
        on. Call :meth:`normalize` again without **strict** to ignore them.

        :param bool strict: Require a normalized filename.
        :raises InvalidWheelFilename: If a part is not valid.
        :raises ExceptionGroup: If **strict** is true and the filename is not
            normalized.

        >>> from packaging.filenames import WheelFilename
        >>> wf = WheelFilename.from_filename("Foo-1.0-py3-none-any.whl").normalize()
        >>> wf.name
        'foo'
        >>> wf.version
        <Version('1.0')>
        >>> sorted(map(str, wf.tags))
        ['py3-none-any']
        """
        result = NormalizedWheelFilename.__new__(NormalizedWheelFilename)
        (
            result._name,
            result._version,
            result._build_tag,
            result._tags,
            result._variant,
            issues,
        ) = _parse_wheel_parts(self._filename, self._parts)
        # The release-only check is fast, and str(version) is slow.
        if strict and (
            issues or _normalized_release_regex.fullmatch(self._parts[1]) is None
        ):
            self._check_normalized(result, issues)
        return result

    def _check_normalized(self, result: NormalizedWheelFilename, issues: int) -> None:
        filename = self._filename
        name, version_part, build, tag_str, _ = self._parts
        # This is a hot path, so it avoids the on_exit context manager.
        collector = _ErrorCollector()
        fixable = True
        if issues & _ISSUE_NAME:
            if _validate_regex.fullmatch(name) is None:
                inner = f"invalid project name {name!r}"
                msg = f"Invalid wheel filename ({inner}): {filename!r}"
                collector.error(InvalidProjectName(msg))
                fixable = False
            else:
                expected = result.name.replace("-", "_")
                inner = f"non-normalized project name {name!r}, should be {expected!r}"
                msg = f"Invalid wheel filename ({inner}): {filename!r}"
                collector.error(NonNormalizedName(msg))
        if not _is_normalized_version(version_part, result.version):
            inner = (
                f"non-normalized version {version_part!r}, "
                f"should be {str(result.version)!r}"
            )
            msg = f"Invalid wheel filename ({inner}): {filename!r}"
            collector.error(NonNormalizedVersion(msg))
        if issues & _ISSUE_BUILD and build != result.build_str:
            inner = (
                f"non-normalized build tag {build!r}, should be {result.build_str!r}"
            )
            msg = f"Invalid wheel filename ({inner}): {filename!r}"
            collector.error(NonNormalizedBuildTag(msg))
        if issues & _ISSUE_TAGS:
            # The tags were parsed already. The string is the compressed form
            # if each component is lowercase, sorted, and has no duplicates.
            components = [part.split(".") for part in tag_str.split("-")]
            if any(part != sorted(part) for part in components):
                msg = (
                    "Invalid wheel filename (compressed tag set components must "
                    "be in sorted order per PEP 425, should be "
                    f"{result.compressed_tags!r}): {filename!r}"
                )
                collector.error(UnsortedWheelTags(msg))
            elif tag_str != tag_str.lower() or any(
                len(part) != len(set(part)) for part in components
            ):
                inner = (
                    f"non-normalized tags {tag_str!r}, "
                    f"should be {result.compressed_tags!r}"
                )
                msg = f"Invalid wheel filename ({inner}): {filename!r}"
                collector.error(NonNormalizedTags(msg))
        if collector.errors:
            msg = f"Non-normalized wheel filename: {filename!r}"
            # An invalid project name has no normalized form.
            if fixable:
                msg += f", should be {result.to_filename()!r}"
            collector.finalize(msg)


class NormalizedWheelFilename:
    """The parsed and normalized parts of a wheel filename.

    Use :meth:`WheelFilename.normalize` to get one from a filename.

    Instances are immutable and hashable. Two instances are equal if their
    name, version, build tag, tags, and variant are equal.

    Instances are safe to serialize with :mod:`pickle`. They use a stable
    format so the same pickle can be loaded in future packaging releases.

    .. versionadded:: 26.4
    """

    __slots__ = ("_build_tag", "_name", "_tags", "_variant", "_version")
    __match_args__ = ("name", "version", "tags")

    def __init__(
        self,
        name: str,
        version: Version,
        tags: Iterable[Tag],
        *,
        build_tag: BuildTag = (),
        variant: str | None = None,
    ) -> None:
        """Create a normalized wheel filename from its component parts.

        :param name: The project name. It is stored in normalized form.
        :param version: The version.
        :param tags: The wheel tag set. It must not be empty, and it must
            contain every combination of its interpreters, ABIs, and platforms.
        :param build_tag: Optional wheel build tag.
        :param variant: The variant label (see :pep:`825`), or ``None``.
        :raises InvalidWheelFilename: If the name is not valid, or the parts
            do not make a filename that parses to the same parts.
        """
        try:
            self._name = canonicalize_name(name, validate=True)
        except InvalidName:
            msg = f"Invalid wheel filename (invalid project name {name!r})"
            raise InvalidWheelFilename(msg) from None
        self._version = version
        self._tags = frozenset(tags)
        self._build_tag = build_tag
        self._variant = variant
        filename = self.to_filename()
        parsed = _parse_wheel_parts(filename, _split_wheel_filename(filename))
        if parsed[:5] != (self._name, version, build_tag, self._tags, variant):
            msg = (
                "Invalid wheel filename (the filename does not parse to the "
                f"given parts): {filename!r}"
            )
            raise InvalidWheelFilename(msg)

    def __replace__(self, **changes: Unpack[_WheelChanges]) -> Self:
        """
        __replace__(*, name=..., version=..., tags=..., build_tag=..., variant=...)

        Return a new normalized wheel filename with parts replaced.

        >>> from packaging.filenames import NormalizedWheelFilename
        >>> from packaging.tags import Tag
        >>> from packaging.version import Version
        >>> tags = {Tag("py3", "none", "any")}
        >>> wf = NormalizedWheelFilename("foo", Version("1.0"), tags)
        >>> wf.__replace__(version=Version("2.0")).to_filename()
        'foo-2.0-py3-none-any.whl'

        :raises InvalidWheelFilename: If the new parts are not valid.
        """
        parts: _WheelChanges = {
            "name": self._name,
            "version": self._version,
            "tags": self._tags,
            "build_tag": self._build_tag,
            "variant": self._variant,
        }
        parts.update(changes)
        return type(self)(**parts)

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
        >>> wf = WheelFilename.from_filename("foo-1.0-py3.py2-none-any.whl")
        >>> wf.normalize().compressed_tags
        'py2.py3-none-any'
        """
        tags = self._tags
        return "-".join(
            ".".join(sorted(part))
            for part in (
                {tag.interpreter for tag in tags},
                {tag.abi for tag in tags},
                {tag.platform for tag in tags},
            )
        )

    @property
    def build_str(self) -> str:
        """The build tag as a string, or an empty string when absent.

        >>> from packaging.filenames import WheelFilename
        >>> wf = WheelFilename.from_filename("foo-1.0-01abc-py3-none-any.whl")
        >>> wf.normalize().build_str
        '1abc'
        """
        return "".join(map(str, self._build_tag))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, NormalizedWheelFilename):
            return NotImplemented
        # str(version) is slow, so it is compared last.
        return (
            self._name == other._name
            and self._build_tag == other._build_tag
            and self._tags == other._tags
            and self._variant == other._variant
            and str(self._version) == str(other._version)
        )

    def __hash__(self) -> int:
        # The version hash is cached, and str(version) is slow.
        return hash(
            (self._name, self._version, self._build_tag, self._tags, self._variant)
        )

    def __getstate__(self) -> str:
        return self.to_filename()

    def __setstate__(self, state: object) -> None:
        filename = _state(type(self), state)
        other = WheelFilename.from_filename(filename).normalize()
        for attr in NormalizedWheelFilename.__slots__:
            setattr(self, attr, getattr(other, attr))

    def __str__(self) -> str:
        return self.to_filename()

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}({self.to_filename()!r})>"

    def to_filename(self) -> str:
        """
        Combines a project name, version, build tag, tag set, and variant label
        to make a properly formatted wheel filename.

        The project name is normalized such that the non-alphanumeric
        characters are replaced with ``_``. The version is normalized. The
        tag set is compressed into a wheel tag string.

        >>> from packaging.filenames import WheelFilename
        >>> wf = WheelFilename.from_filename("Foo.Bar-01.0-py3.py2-none-any.whl")
        >>> wf.normalize().to_filename()
        'foo_bar-1.0-py2.py3-none-any.whl'
        """
        name = self._name.replace("-", "_")
        file_parts = [name, str(self._version)]
        if self._build_tag:
            file_parts.append(self.build_str)
        file_parts.append(self.compressed_tags)
        if self._variant is not None:
            file_parts.append(self._variant)
        return "-".join(file_parts) + ".whl"


class SourceDistributionFilename:
    """A source distribution filename, split into its parts as they are written.

    Only the structure of the filename is checked. Call :meth:`normalize` to
    check the parts and get a :class:`NormalizedSdistFilename`.

    Instances are immutable and hashable. Two instances are equal if their
    filenames are equal.

    Instances are safe to serialize with :mod:`pickle`. They use a stable
    format so the same pickle can be loaded in future packaging releases.

    .. versionadded:: 26.4
    """

    __slots__ = ("_filename", "_parts")
    __match_args__ = ("name", "version")

    def __init__(self, name: str, version: str, *, extension: str = ".tar.gz") -> None:
        """Create a source distribution filename from its parts, as they are written.

        :param name: The project name.
        :param version: The version.
        :param extension: The extension, ``".tar.gz"`` or the legacy ``".zip"``.
        :raises InvalidSdistFilename: If the parts do not make a filename that
            splits into the same parts.
        """
        parts = (name, version, extension)
        filename = f"{name}-{version}{extension}"
        if _split_sdist_filename(filename) != parts:
            msg = (
                "Invalid sdist filename (the filename does not split into the "
                f"given parts): {filename!r}"
            )
            raise InvalidSdistFilename(msg)
        self._filename = filename
        self._parts = parts

    @classmethod
    def from_filename(cls, filename: str, /) -> Self:
        """
        Split the filename of a sdist file (as specified in the `Source
        distribution format`_ documentation) into its parts.

        The parts are not checked. Call :meth:`normalize` to check them.

        :param str filename: The name of the sdist file.
        :raises InvalidSdistFilename: If the filename does not end
            with an sdist extension (``.zip`` or ``.tar.gz``), if it does not
            contain a dash separating the name and the version of the
            distribution, or if the project name is empty.

        >>> from packaging.filenames import SourceDistributionFilename
        >>> fn = SourceDistributionFilename.from_filename("Foo-1.0.tar.gz")
        >>> fn.name
        'Foo'
        >>> fn.version
        '1.0'

        .. _Source distribution format: https://packaging.python.org/specifications/source-distribution-format/#source-distribution-file-name
        """
        self = cls.__new__(cls)
        self._filename = filename
        self._parts = _split_sdist_filename(filename)
        return self

    def __replace__(self, **changes: Unpack[_RawSdistChanges]) -> Self:
        """
        __replace__(*, name=..., version=..., extension=...)

        Return a new sdist filename with parts replaced. The other parts are
        kept as written.

        >>> from packaging.filenames import SourceDistributionFilename
        >>> fn = SourceDistributionFilename.from_filename("Foo-1.0.zip")
        >>> fn.__replace__(version="2.0").to_filename()
        'Foo-2.0.zip'

        :raises InvalidSdistFilename: If the new parts do not make a filename
            that splits into the same parts.
        """
        name, version, extension = self._parts
        parts: _RawSdistChanges = {
            "name": name,
            "version": version,
            "extension": extension,
        }
        parts.update(changes)
        return type(self)(**parts)

    @property
    def name(self) -> str:
        """The project name, as written."""
        return self._parts[0]

    @property
    def version(self) -> str:
        """The version, as written."""
        return self._parts[1]

    @property
    def extension(self) -> str:
        """The extension, ``".tar.gz"`` or the legacy ``".zip"``."""
        return self._parts[2]

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SourceDistributionFilename):
            return NotImplemented
        return self._filename == other._filename

    def __hash__(self) -> int:
        return hash(self._filename)

    def __getstate__(self) -> str:
        return self._filename

    def __setstate__(self, state: object) -> None:
        self._filename = _state(type(self), state)
        self._parts = _split_sdist_filename(self._filename)

    def __str__(self) -> str:
        return self._filename

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}({self._filename!r})>"

    def to_filename(self) -> str:
        """The filename, as written.

        >>> from packaging.filenames import SourceDistributionFilename
        >>> SourceDistributionFilename("Foo", "01.0").to_filename()
        'Foo-01.0.tar.gz'
        """
        return self._filename

    def normalize(self, *, strict: bool = False) -> NormalizedSdistFilename:
        """
        Parse the parts into a :class:`NormalizedSdistFilename`.

        Parsing accepts legacy names, versions, and the ``.zip`` extension.
        With **strict**, the filename must also be in its normalized form: the
        extension must be ``.tar.gz``, and the name and version must be
        normalized.

        Normalization errors are collected into an
        :external:exc:`ExceptionGroup`. Each problem has its own exception
        class, such as :class:`NonNormalizedName`, so ``except*`` can select
        the checks to act on. Call :meth:`normalize` again without **strict**
        to ignore them.

        :param bool strict: Require a normalized filename.
        :raises InvalidSdistFilename: If the version is not valid.
        :raises ExceptionGroup: If **strict** is true and the filename is not
            normalized.

        >>> from packaging.filenames import SourceDistributionFilename
        >>> fn = SourceDistributionFilename.from_filename("Foo-1.0.tar.gz").normalize()
        >>> fn.name
        'foo'
        >>> fn.version
        <Version('1.0')>
        """
        filename = self._filename
        name_part, version_part, _ = self._parts
        result = NormalizedSdistFilename.__new__(NormalizedSdistFilename)
        try:
            result._version = Version(version_part)
        except InvalidVersion as e:
            inner = f"invalid version {version_part!r}"
            msg = f"Invalid sdist filename ({inner}): {filename!r}"
            raise InvalidSdistFilename(msg) from e
        result._name = canonicalize_name(name_part)
        if strict:
            self._check_normalized(result)
        return result

    def _check_normalized(self, result: NormalizedSdistFilename) -> None:
        filename = self._filename
        name_part, version_part, ext = self._parts
        # This is a hot path, so it avoids the on_exit context manager.
        collector = _ErrorCollector()
        fixable = True
        if ext != ".tar.gz":
            msg = f"Invalid sdist filename (extension must be '.tar.gz'): {filename!r}"
            collector.error(ZipSdistFilename(msg))
        if _normalized_wheel_name_regex.fullmatch(name_part) is None:
            # A valid name that fails the fast check is not normalized.
            if _validate_regex.fullmatch(name_part) is None:
                inner = f"invalid project name {name_part!r}"
                msg = f"Invalid sdist filename ({inner}): {filename!r}"
                collector.error(InvalidProjectName(msg))
                fixable = False
            else:
                expected = result.name.replace("-", "_")
                inner = (
                    f"non-normalized project name {name_part!r}, should be {expected!r}"
                )
                msg = f"Invalid sdist filename ({inner}): {filename!r}"
                collector.error(NonNormalizedName(msg))
        if not _is_normalized_version(version_part, result.version):
            inner = (
                f"non-normalized version {version_part!r}, "
                f"should be {str(result.version)!r}"
            )
            msg = f"Invalid sdist filename ({inner}): {filename!r}"
            collector.error(NonNormalizedVersion(msg))
        if collector.errors:
            msg = f"Non-normalized sdist filename: {filename!r}"
            # An invalid project name has no normalized form.
            if fixable:
                msg += f", should be {result.to_filename()!r}"
            collector.finalize(msg)


class NormalizedSdistFilename:
    """The parsed and normalized parts of a source distribution filename.

    Use :meth:`SourceDistributionFilename.normalize` to get one from a
    filename.

    Instances are immutable and hashable. Two instances are equal if their
    name and version are equal.

    Instances are safe to serialize with :mod:`pickle`. They use a stable
    format so the same pickle can be loaded in future packaging releases.

    .. versionadded:: 26.4
    """

    __slots__ = ("_name", "_version")
    __match_args__ = ("name", "version")

    def __init__(self, name: str, version: Version) -> None:
        """Create a normalized source distribution filename.

        :param str name: The project name. It is stored in normalized form.
        :param version: The version.
        :raises InvalidSdistFilename: If the name is not valid, or the parts
            do not make a filename that parses to the same parts.
        """
        try:
            self._name = canonicalize_name(name, validate=True)
        except InvalidName:
            msg = f"Invalid sdist filename (invalid project name {name!r})"
            raise InvalidSdistFilename(msg) from None
        self._version = version
        filename = self.to_filename()
        if parse_sdist_filename(filename) != (self._name, version):
            msg = (
                "Invalid sdist filename (the filename does not parse to the "
                f"given parts): {filename!r}"
            )
            raise InvalidSdistFilename(msg)

    def __replace__(self, **changes: Unpack[_SdistChanges]) -> Self:
        """
        __replace__(*, name=..., version=...)

        Return a new normalized sdist filename with parts replaced.

        >>> from packaging.filenames import NormalizedSdistFilename
        >>> from packaging.version import Version
        >>> fn = NormalizedSdistFilename("foo", Version("1.0"))
        >>> fn.__replace__(version=Version("2.0")).to_filename()
        'foo-2.0.tar.gz'

        :raises InvalidSdistFilename: If the new parts are not valid.
        """
        parts: _SdistChanges = {"name": self._name, "version": self._version}
        parts.update(changes)
        return type(self)(**parts)

    @property
    def name(self) -> NormalizedName:
        """The normalized project name."""
        return self._name

    @property
    def version(self) -> Version:
        """The parsed project version."""
        return self._version

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, NormalizedSdistFilename):
            return NotImplemented
        # str(version) is slow, so it is compared last.
        return self._name == other._name and str(self._version) == str(other._version)

    def __hash__(self) -> int:
        # The version hash is cached, and str(version) is slow.
        return hash((self._name, self._version))

    def __getstate__(self) -> str:
        return self.to_filename()

    def __setstate__(self, state: object) -> None:
        filename = _state(type(self), state)
        self._name, self._version = parse_sdist_filename(filename)

    def __str__(self) -> str:
        return self.to_filename()

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}({self.to_filename()!r})>"

    def to_filename(self) -> str:
        """
        Combines the project name and a version to make a valid sdist filename. The
        project name is normalized as required so that any run of ``-._``
        characters are replaced with ``_`` and characters are lower cased. The
        version is normalized.

        >>> from packaging.filenames import SourceDistributionFilename
        >>> SourceDistributionFilename("Foo-Bar", "01.0").normalize().to_filename()
        'foo_bar-1.0.tar.gz'
        """
        name = self._name.replace("-", "_")
        return f"{name}-{self._version}.tar.gz"
