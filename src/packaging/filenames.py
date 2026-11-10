# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

from .errors import _ErrorCollector
from .tags import InvalidTag, parse_tag
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
    _parse_build_tag,
    _parse_wheel_filename,
    _split_wheel_filename,
    _validate_regex,
    _variant_label_regex,
    canonicalize_name,
    parse_sdist_filename,
)
from .version import InvalidVersion, Version

if TYPE_CHECKING:
    from collections.abc import Iterable

    from typing_extensions import Self, Unpack

    from .tags import Tag
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


class _SdistReplace(TypedDict, total=False):
    name: str
    version: Version | str


class _WheelReplace(_SdistReplace, total=False):
    build_tag: BuildTag | str
    tags: Iterable[Tag] | str
    variant: str | None


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

    __slots__ = (
        "_build_tag",
        "_filename",
        "_issues",
        "_name",
        "_tags",
        "_variant",
        "_version",
    )
    __match_args__ = ("name", "version", "tags")

    def __init__(
        self,
        name: str,
        version: Version | str,
        tags: Iterable[Tag] | str,
        *,
        build_tag: BuildTag | str = (),
        variant: str | None = None,
    ) -> None:
        """Create a wheel filename from its component parts.

        :param name: The project name. It is stored in normalized form.
        :param version: The version.
        :param tags: The wheel tag set, or a compressed tag string like
            ``"py2.py3-none-any"``. It must not be empty, and it must
            contain every combination of its interpreters, ABIs, and platforms.
            Each tag must be valid in a filename (see
            :func:`~packaging.tags.parse_tag`).
        :param build_tag: Optional wheel build tag, as a tuple or as a string
            like ``"1abc"``.
        :param variant: The variant label (see :pep:`825`), or ``None``.
        :raises InvalidWheelFilename: If the name, version, tag set, build tag,
            or variant label is not valid.
        """
        self._filename: str | None = None
        self._issues = 0
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
            if isinstance(build_tag, str):
                parsed = _parse_build_tag(build_tag)
                if build_tag and not parsed:
                    msg = f"Invalid wheel filename (invalid build tag {build_tag!r})"
                    raise InvalidWheelFilename(msg)
                build_tag = parsed
            # The build tag must round-trip through the filename string.
            elif build_tag and (
                type(build_tag[0]) is not int
                or _parse_build_tag("".join(map(str, build_tag))) != build_tag
            ):
                msg = f"Invalid wheel filename (invalid build tag {build_tag!r})"
                raise InvalidWheelFilename(msg)
            self._build_tag = build_tag
        if "tags" in kwargs:
            new_tags = kwargs["tags"]
            if isinstance(new_tags, str):
                try:
                    new_tags = parse_tag(new_tags)
                except InvalidTag:
                    msg = f"Invalid wheel filename (invalid tag {new_tags!r})"
                    raise InvalidWheelFilename(msg) from None
            tags = frozenset(new_tags)
            # Each tag must parse back to itself, so the filename round-trips.
            # These are the rules of parse_tag for one tag.
            for tag in tags:
                abi_platform = tag.abi + tag.platform
                if not (
                    tag.interpreter.isidentifier()
                    and tag.abi
                    and tag.platform
                    and "." not in abi_platform
                    and "-" not in abi_platform
                ):
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
        new._issues = 0
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

    @property
    def original_name(self) -> str | None:
        """The name as written in :attr:`original_filename`, or ``None``.

        Use this with :attr:`original_version` to find the ``.dist-info``
        directory, or to keep the original spelling when you rename a wheel.

        >>> from packaging.filenames import WheelFilename
        >>> WheelFilename.from_filename("Foo.Bar-1.0-py3-none-any.whl").original_name
        'Foo.Bar'
        """
        if self._filename is None:
            return None
        return _split_wheel_filename(self._filename)[0]

    @property
    def original_version(self) -> str | None:
        """The version as written in :attr:`original_filename`, or ``None``.

        >>> from packaging.filenames import WheelFilename
        >>> WheelFilename.from_filename("foo-01.0-py3-none-any.whl").original_version
        '01.0'
        """
        if self._filename is None:
            return None
        return _split_wheel_filename(self._filename)[1]

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, WheelFilename):
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

    def __getstate__(self) -> tuple[str, bool]:
        # The flag records if the filename is the original one.
        if self._filename is None:
            return self.to_filename(), False
        return self._filename, True

    def __setstate__(self, state: object) -> None:
        if not (
            isinstance(state, tuple)
            and len(state) == 2
            and isinstance(state[0], str)
            and isinstance(state[1], bool)
        ):
            raise TypeError(f"Cannot restore {type(self).__name__} from {state!r}")
        filename, original = state
        other = type(self).from_filename(filename)
        for attr in WheelFilename.__slots__:
            setattr(self, attr, getattr(other, attr))
        if not original:
            self._filename = None
            self._issues = 0

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
            self._issues,
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
        issues = self._issues
        # The release-only check is fast, and str(version) is slow.
        if not issues and _normalized_release_regex.fullmatch(version_part):
            return
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
                expected = self._name.replace("-", "_")
                inner = f"non-normalized project name {name!r}, should be {expected!r}"
                msg = f"Invalid wheel filename ({inner}): {filename!r}"
                collector.error(NonNormalizedName(msg))
        if not _is_normalized_version(version_part, self._version):
            inner = (
                f"non-normalized version {version_part!r}, "
                f"should be {str(self._version)!r}"
            )
            msg = f"Invalid wheel filename ({inner}): {filename!r}"
            collector.error(NonNormalizedVersion(msg))
        if issues & _ISSUE_BUILD and build != self.build_str:
            inner = f"non-normalized build tag {build!r}, should be {self.build_str!r}"
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
                    f"{self.compressed_tags!r}): {filename!r}"
                )
                collector.error(UnsortedWheelTags(msg))
            elif tag_str != tag_str.lower() or any(
                len(part) != len(set(part)) for part in components
            ):
                inner = (
                    f"non-normalized tags {tag_str!r}, "
                    f"should be {self.compressed_tags!r}"
                )
                msg = f"Invalid wheel filename ({inner}): {filename!r}"
                collector.error(NonNormalizedTags(msg))
        if collector.errors:
            msg = f"Non-normalized wheel filename: {filename!r}"
            # An invalid project name has no normalized form.
            if fixable:
                msg += f", should be {self.to_filename()!r}"
            collector.finalize(msg)


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

    def _original_parts(self) -> tuple[str, str] | None:
        filename = self._filename
        if filename is None:
            return None
        ext = ".tar.gz" if filename.endswith(".tar.gz") else ".zip"
        name_part, _, version_part = filename[: -len(ext)].rpartition("-")
        return name_part, version_part

    @property
    def original_name(self) -> str | None:
        """The name as written in :attr:`original_filename`, or ``None``.

        >>> from packaging.filenames import SourceDistributionFilename
        >>> SourceDistributionFilename.from_filename("Foo-1.0.tar.gz").original_name
        'Foo'
        """
        parts = self._original_parts()
        return None if parts is None else parts[0]

    @property
    def original_version(self) -> str | None:
        """The version as written in :attr:`original_filename`, or ``None``.

        >>> from packaging.filenames import SourceDistributionFilename
        >>> fn = SourceDistributionFilename.from_filename("foo-01.0.tar.gz")
        >>> fn.original_version
        '01.0'
        """
        parts = self._original_parts()
        return None if parts is None else parts[1]

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SourceDistributionFilename):
            return NotImplemented
        # str(version) is slow, so it is compared last.
        return self._name == other._name and str(self._version) == str(other._version)

    def __hash__(self) -> int:
        # The version hash is cached, and str(version) is slow.
        return hash((self._name, self._version))

    def __getstate__(self) -> tuple[str, bool]:
        # The flag records if the filename is the original one.
        if self._filename is None:
            return self.to_filename(), False
        return self._filename, True

    def __setstate__(self, state: object) -> None:
        if not (
            isinstance(state, tuple)
            and len(state) == 2
            and isinstance(state[0], str)
            and isinstance(state[1], bool)
        ):
            raise TypeError(f"Cannot restore {type(self).__name__} from {state!r}")
        filename, original = state
        other = type(self).from_filename(filename)
        for attr in SourceDistributionFilename.__slots__:
            setattr(self, attr, getattr(other, attr))
        if not original:
            self._filename = None

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
        self._name, self._version = parse_sdist_filename(filename)
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
        parts = self._original_parts()
        if filename is None or parts is None:
            return
        name_part, version_part = parts
        # This is a hot path, so it avoids the on_exit context manager.
        collector = _ErrorCollector()
        fixable = True
        if not filename.endswith(".tar.gz"):
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
                expected = self._name.replace("-", "_")
                inner = (
                    f"non-normalized project name {name_part!r}, should be {expected!r}"
                )
                msg = f"Invalid sdist filename ({inner}): {filename!r}"
                collector.error(NonNormalizedName(msg))
        if not _is_normalized_version(version_part, self._version):
            inner = (
                f"non-normalized version {version_part!r}, "
                f"should be {str(self._version)!r}"
            )
            msg = f"Invalid sdist filename ({inner}): {filename!r}"
            collector.error(NonNormalizedVersion(msg))
        if collector.errors:
            msg = f"Non-normalized sdist filename: {filename!r}"
            # An invalid project name has no normalized form.
            if fixable:
                msg += f", should be {self.to_filename()!r}"
            collector.finalize(msg)
