from __future__ import annotations

import email.feedparser
import email.header
import email.message
import email.parser
import email.policy
import keyword
import pathlib
import sys
import typing
from typing import (
    Any,
    Callable,
    Generic,
    Literal,
    TypedDict,
    cast,
)

from . import licenses, requirements, specifiers, utils
from . import version as version_module
from .licenses import NormalizedLicenseExpression

T = typing.TypeVar("T")


if sys.version_info >= (3, 11):  # pragma: no cover
    ExceptionGroup = ExceptionGroup  # noqa: F821
else:  # pragma: no cover

    class ExceptionGroup(Exception):
        """A minimal implementation of :external:exc:`ExceptionGroup` from Python 3.11.

        If :external:exc:`ExceptionGroup` is already defined by Python itself,
        that version is used instead.
        """

        message: str
        exceptions: list[Exception]

        def __init__(self, message: str, exceptions: list[Exception]) -> None:
            self.message = message
            self.exceptions = exceptions
            super().__init__(message)

        def __repr__(self) -> str:
            return f"{self.__class__.__name__}({self.message!r}, {self.exceptions!r})"






class InvalidMetadata(ValueError):
    """A metadata field contains invalid data."""

    field: str
    """The name of the field that contains invalid data."""

    def __init__(self, field: str, message: str) -> None:
        self.field = field
        super().__init__(message)


# The RawMetadata class attempts to make as few assumptions about the underlying
# serialization formats as possible. The idea is that as long as a serialization
# formats offer some very basic primitives in *some* way then we can support
# serializing to and from that format.
class RawMetadata(TypedDict, total=False):
    """A dictionary of raw core metadata.

    Each field in core metadata maps to a key of this dictionary (when data is
    provided). The key is lower-case and underscores are used instead of dashes
    compared to the equivalent core metadata field. Any core metadata field that
    can be specified multiple times or can hold multiple values in a single
    field have a key with a plural name. See :class:`Metadata` whose attributes
    match the keys of this dictionary.

    Core metadata fields that can be specified multiple times are stored as a
    list or dict depending on which is appropriate for the field. Any fields
    which hold multiple values in a single field are stored as a list.

    """

    # Metadata 1.0 - PEP 241
    metadata_version: str
    name: str
    version: str
    platforms: list[str]
    summary: str
    description: str
    keywords: list[str]
    home_page: str
    author: str
    author_email: str
    license: str

    # Metadata 1.1 - PEP 314
    supported_platforms: list[str]
    download_url: str
    classifiers: list[str]
    requires: list[str]
    provides: list[str]
    obsoletes: list[str]

    # Metadata 1.2 - PEP 345
    maintainer: str
    maintainer_email: str
    requires_dist: list[str]
    provides_dist: list[str]
    obsoletes_dist: list[str]
    requires_python: str
    requires_external: list[str]
    project_urls: dict[str, str]

    # Metadata 2.0
    # PEP 426 attempted to completely revamp the metadata format
    # but got stuck without ever being able to build consensus on
    # it and ultimately ended up withdrawn.
    #
    # However, a number of tools had started emitting METADATA with
    # `2.0` Metadata-Version, so for historical reasons, this version
    # was skipped.

    # Metadata 2.1 - PEP 566
    description_content_type: str
    provides_extra: list[str]

    # Metadata 2.2 - PEP 643
    dynamic: list[str]

    # Metadata 2.3 - PEP 685
    # No new fields were added in PEP 685, just some edge case were
    # tightened up to provide better interoptability.

    # Metadata 2.4 - PEP 639
    license_expression: str
    license_files: list[str]

    # Metadata 2.5 - PEP 794
    import_names: list[str]
    import_namespaces: list[str]


# 'keywords' is special as it's a string in the core metadata spec, but we
# represent it as a list.
_STRING_FIELDS = {
    "author",
    "author_email",
    "description",
    "description_content_type",
    "download_url",
    "home_page",
    "license",
    "license_expression",
    "maintainer",
    "maintainer_email",
    "metadata_version",
    "name",
    "requires_python",
    "summary",
    "version",
}

_LIST_FIELDS = {
    "classifiers",
    "dynamic",
    "license_files",
    "obsoletes",
    "obsoletes_dist",
    "platforms",
    "provides",
    "provides_dist",
    "provides_extra",
    "requires",
    "requires_dist",
    "requires_external",
    "supported_platforms",
    "import_names",
    "import_namespaces",
}

_DICT_FIELDS = {
    "project_urls",
}


def _parse_keywords(data: str) -> list[str]:
    return [k.strip() for k in data.split(",")]


def _parse_project_urls(data: list[str]) -> dict[str, str]:
    urls: dict[str, str] = {}
    for pair in data:
        label, _, url = pair.partition(",")
        label = label.strip()
        url = url.strip()
        if label in urls:
            raise KeyError(label)
        urls[label] = url
    return urls


def _get_payload(
    msg: email.message.Message, source: bytes | str
) -> str | None:
    if isinstance(source, bytes):
        payload: str | None = msg.get_payload(decode=True).decode("utf-8")  # type: ignore[union-attr]
    else:
        payload = msg.get_payload()
    if payload:
        return payload
    return None
































































# The various parse_FORMAT functions here are intended to be as lenient as
# possible in their parsing, while still returning a correctly typed
# RawMetadata.
#
# To aid in this, we also generally want to do as little touching of the
# data as possible, except where there are possibly some historic holdovers
# that make valid data awkward to work with.
#
# While this is a lower level, intermediate format than our ``Metadata``
# class, some light touch ups can make a massive difference in usability.

# Map METADATA fields to RawMetadata.
_EMAIL_TO_RAW_MAPPING = {
    "author": "author",
    "author-email": "author_email",
    "classifier": "classifiers",
    "description": "description",
    "description-content-type": "description_content_type",
    "download-url": "download_url",
    "dynamic": "dynamic",
    "home-page": "home_page",
    "import-name": "import_names",
    "import-namespace": "import_namespaces",
    "keywords": "keywords",
    "license": "license",
    "license-expression": "license_expression",
    "license-file": "license_files",
    "maintainer": "maintainer",
    "maintainer-email": "maintainer_email",
    "metadata-version": "metadata_version",
    "name": "name",
    "obsoletes": "obsoletes",
    "obsoletes-dist": "obsoletes_dist",
    "platform": "platforms",
    "project-url": "project_urls",
    "provides": "provides",
    "provides-dist": "provides_dist",
    "provides-extra": "provides_extra",
    "requires": "requires",
    "requires-dist": "requires_dist",
    "requires-external": "requires_external",
    "requires-python": "requires_python",
    "summary": "summary",
    "supported-platform": "supported_platforms",
    "version": "version",
}
_RAW_TO_EMAIL_MAPPING = {raw: email for email, raw in _EMAIL_TO_RAW_MAPPING.items()}


# This class is for writing RFC822 messages
class RFC822Policy(email.policy.EmailPolicy):
    """
    This is :class:`email.policy.EmailPolicy`, but with a simple ``header_store_parse``
    implementation that handles multi-line values, and some nice defaults.
    """

    utf8 = True
    mangle_from_ = False
    max_line_length = 0

    def header_store_parse(self, name: str, value: str) -> tuple[str, str]:
        if "\n" in value:
            value = value.replace("\n", "\n" + " " * 8 + "\t")
        return (name, value)





# This class is for writing RFC822 messages
class RFC822Message(email.message.EmailMessage):
    """
    This is :class:`email.message.EmailMessage` with two small changes: it defaults to
    our `RFC822Policy`, and it correctly writes unicode when being called
    with `bytes()`.
    """

    def __init__(self) -> None:
        super().__init__(policy=RFC822Policy())

    def as_bytes(
        self,
        unixfrom: bool = False,
        policy: email.policy.Policy | None = None,
    ) -> bytes:
        return self.as_string(unixfrom=unixfrom, policy=policy).encode("utf-8")


def parse_email(
    data: bytes | str,
) -> tuple[RawMetadata, dict[str, list[str]]]:
    raw: dict[str, Any] = {}
    unparsed: dict[str, list[str]] = {}

    if isinstance(data, bytes):
        msg = email.parser.BytesParser(policy=email.policy.compat32).parsebytes(data)
    else:
        msg = email.parser.Parser(policy=email.policy.compat32).parsestr(data)

    for name in msg.keys():
        raw_name = name.lower().replace("-", "_")
        mapped_name = _EMAIL_TO_RAW_MAPPING.get(name.lower().replace("_", "-"))
        if mapped_name is None:
            if raw_name not in unparsed:
                unparsed[raw_name] = []
            values = msg.get_all(name)
            if values:
                for v in values:
                    if isinstance(v, email.header.Header):
                        unparsed[raw_name].append(str(v))
                    else:
                        unparsed[raw_name].append(v)
            continue

    for name in dict.fromkeys(msg.keys()):
        norm_name = name.lower().replace("_", "-")
        mapped_name = _EMAIL_TO_RAW_MAPPING.get(norm_name)
        if mapped_name is None:
            continue

        values = msg.get_all(name)
        if values is None:
            continue

        str_values: list[str] = []
        valid_encoding = True
        for val in values:
            if isinstance(val, email.header.Header):
                chunks = email.header.decode_header(val)
                new_chunks: list[tuple[bytes | str, str | None]] = []
                for chunk_bytes, chunk_encoding in chunks:
                    if isinstance(chunk_bytes, bytes):
                        try:
                            chunk_bytes.decode("utf-8")
                            new_chunks.append((chunk_bytes, chunk_encoding or "utf-8"))
                        except UnicodeDecodeError:
                            valid_encoding = False
                            new_chunks.append((chunk_bytes, "latin-1"))
                    else:
                        new_chunks.append((chunk_bytes, chunk_encoding))
                reconstructed = str(email.header.make_header(new_chunks))
                str_values.append(reconstructed)
            else:
                str_values.append(val)

        if not valid_encoding:
            unparsed.setdefault(mapped_name, []).extend(str_values)
            continue

        if mapped_name in _STRING_FIELDS:
            if len(str_values) == 1:
                if mapped_name not in raw:
                    raw[mapped_name] = str_values[0]
                else:
                    unparsed.setdefault(mapped_name, [])
                    if isinstance(raw[mapped_name], str):
                        unparsed[mapped_name].append(raw[mapped_name])
                    del raw[mapped_name]
                    unparsed[mapped_name].extend(str_values)
            else:
                if mapped_name in raw:
                    unparsed.setdefault(mapped_name, [])
                    if isinstance(raw[mapped_name], str):
                        unparsed[mapped_name].append(raw[mapped_name])
                    del raw[mapped_name]
                unparsed.setdefault(mapped_name, []).extend(str_values)
        elif mapped_name in _LIST_FIELDS:
            raw.setdefault(mapped_name, []).extend(str_values)
        elif mapped_name in _DICT_FIELDS:
            raw.setdefault(mapped_name, []).extend(str_values)

    if "keywords" in raw and isinstance(raw["keywords"], str):
        raw["keywords"] = _parse_keywords(raw["keywords"])

    if "project_urls" in raw and isinstance(raw["project_urls"], list):
        try:
            raw["project_urls"] = _parse_project_urls(raw["project_urls"])
        except KeyError:
            unparsed.setdefault("project_urls", []).extend(raw["project_urls"])
            del raw["project_urls"]

    body = _get_payload(msg, data)
    if body:
        if "description" in raw:
            unparsed.setdefault("description", [])
            unparsed["description"].append(raw["description"])
            unparsed["description"].append(body)
            del raw["description"]
        else:
            raw["description"] = body

    return cast(RawMetadata, raw), unparsed





























































































































































































_NOT_FOUND = object()


# Keep the two values in sync.
_VALID_METADATA_VERSIONS = ["1.0", "1.1", "1.2", "2.1", "2.2", "2.3", "2.4", "2.5"]
_MetadataVersion = Literal["1.0", "1.1", "1.2", "2.1", "2.2", "2.3", "2.4", "2.5"]

_REQUIRED_ATTRS = frozenset(["metadata_version", "name", "version"])


class _Validator(Generic[T]):
    """Validate a metadata field.

    All _process_*() methods correspond to a core metadata field. The method is
    called with the field's raw value. If the raw value is valid it is returned
    in its "enriched" form (e.g. ``version.Version`` for the ``Version`` field).
    If the raw value is invalid, :exc:`InvalidMetadata` is raised (with a cause
    as appropriate).
    """

    name: str
    raw_name: str
    added: _MetadataVersion

    def __init__(
        self,
        *,
        added: _MetadataVersion = "1.0",
    ) -> None:
        self.added = added

    def __set_name__(self, _owner: Metadata, name: str) -> None:
        self.name = name
        self.raw_name = _RAW_TO_EMAIL_MAPPING[name]

    def __get__(self, instance: Metadata | None, _owner: type[Metadata]) -> Any:
        if instance is None:
            return self

        try:
            return instance.__dict__[self.name]
        except KeyError:
            pass

        raw_value = instance._raw.get(self.name, _NOT_FOUND)  # type: ignore[literal-required]
        if raw_value is _NOT_FOUND:
            if self.name in _REQUIRED_ATTRS:
                raw_value = _NOT_FOUND
            else:
                return None

        try:
            process = getattr(self, f"_process_{self.name}")
        except AttributeError:
            value = raw_value
        else:
            value = process(raw_value)

        instance.__dict__[self.name] = value
        instance._raw.pop(self.name, None)  # type: ignore[misc]
        return value

    def _invalid_metadata(
        self, msg: str, *, cause: Exception | None = None
    ) -> InvalidMetadata:
        exc = InvalidMetadata(self.raw_name, msg.format(field=self.raw_name))
        exc.__cause__ = cause
        return exc

    def _process_metadata_version(self, value: str) -> _MetadataVersion:
        if value not in _VALID_METADATA_VERSIONS:
            raise self._invalid_metadata(
                f"{{field}} is not a valid metadata version: {value!r}"
            )
        return cast(_MetadataVersion, value)

    def _process_name(self, value: str) -> str:
        if not value:
            raise self._invalid_metadata("{{field}} is a required field")
        try:
            utils.canonicalize_name(value, validate=True)
        except utils.InvalidName as e:
            raise self._invalid_metadata(
                f"{{field}} is invalid: {value!r}"
            ) from e
        return value

    def _process_version(self, value: str) -> version_module.Version:
        if not value:
            raise self._invalid_metadata("{{field}} is a required field")
        try:
            return version_module.Version(value)
        except version_module.InvalidVersion as e:
            raise self._invalid_metadata(
                f"{{field}} is invalid: {value!r}"
            ) from e

    def _process_summary(self, value: str) -> str:
        if "\n" in value:
            raise self._invalid_metadata("{field} must be a single line")
        return value

    def _process_description_content_type(self, value: str) -> str:
        content_type_msg = email.message.EmailMessage()
        content_type_msg["Content-Type"] = value
        content_type = content_type_msg.get_content_type()
        if content_type not in {"text/plain", "text/x-rst", "text/markdown"}:
            raise self._invalid_metadata(
                f"{{field}} must be one of text/plain, text/x-rst, "
                f"text/markdown, not {content_type!r}"
            )
        charset = content_type_msg["Content-Type"].params.get("charset", "UTF-8")
        if charset.upper() != "UTF-8":
            raise self._invalid_metadata(
                f"{{field}} can only specify the UTF-8 charset, not {charset!r}"
            )
        if content_type == "text/markdown":
            variant = content_type_msg["Content-Type"].params.get("variant", "GFM")
            if variant not in {"GFM", "CommonMark"}:
                raise self._invalid_metadata(
                    f"{{field}} variant must be one of GFM or CommonMark, "
                    f"not {variant!r}"
                )
        return value

    def _process_dynamic(self, value: list[str]) -> list[str]:
        dynamic = [v.lower() for v in value]
        for field in dynamic:
            if field in {"name", "version", "metadata-version"}:
                raise self._invalid_metadata(
                    f"{{field}} cannot include {field!r}"
                )
            if field.replace("-", "_") not in _EMAIL_TO_RAW_MAPPING.values():
                raise self._invalid_metadata(
                    f"{{field}} contains an unrecognized field: {field!r}"
                )
        return dynamic

    def _process_provides_extra(
        self, value: list[str]
    ) -> list[utils.NormalizedName]:
        normalized: list[utils.NormalizedName] = []
        for extra in value:
            try:
                normalized.append(utils.canonicalize_name(extra, validate=True))
            except utils.InvalidName as e:
                raise self._invalid_metadata(
                    f"{{field}} contains an invalid extra name: {extra!r}"
                ) from e
        return normalized

    def _process_requires_python(
        self, value: str
    ) -> specifiers.SpecifierSet:
        try:
            return specifiers.SpecifierSet(value)
        except specifiers.InvalidSpecifier as e:
            raise self._invalid_metadata(
                f"{{field}} is invalid: {value!r}"
            ) from e

    def _process_requires_dist(
        self, value: list[str]
    ) -> list[requirements.Requirement]:
        reqs: list[requirements.Requirement] = []
        for req in value:
            try:
                reqs.append(requirements.Requirement(req))
            except requirements.InvalidRequirement as e:
                raise self._invalid_metadata(
                    f"{{field}} contains an invalid requirement: {req!r}"
                ) from e
        return reqs

    def _process_license_expression(
        self, value: str
    ) -> NormalizedLicenseExpression:
        try:
            return licenses.canonicalize_license_expression(value)
        except ValueError as e:
            raise self._invalid_metadata(
                f"{{field}} is invalid: {value!r}"
            ) from e

    def _process_license_files(self, value: list[str]) -> list[str]:
        for path in value:
            if ".." in path:
                raise self._invalid_metadata(
                    f"{{field}} contains an invalid path: {path!r}"
                )
            if "*" in path:
                raise self._invalid_metadata(
                    f"{{field}} contains an invalid path: {path!r}"
                )
            if (
                pathlib.PurePosixPath(path).is_absolute()
                or pathlib.PureWindowsPath(path).is_absolute()
            ):
                raise self._invalid_metadata(
                    f"{{field}} contains an invalid path: {path!r}"
                )
            if "\\" in path:
                raise self._invalid_metadata(
                    f"{{field}} contains an invalid path: {path!r}"
                )
        return value

























































































































































































    def _process_import_names(self, value: list[str]) -> list[str]:
        for import_name in value:
            name, semicolon, private = import_name.partition(";")
            name = name.rstrip()
            for identifier in name.split("."):
                if not identifier.isidentifier():
                    raise self._invalid_metadata(
                        f"{name!r} is invalid for {{field}}; "
                        f"{identifier!r} is not a valid identifier"
                    )
                elif keyword.iskeyword(identifier):
                    raise self._invalid_metadata(
                        f"{name!r} is invalid for {{field}}; "
                        f"{identifier!r} is a keyword"
                    )
            if semicolon and private.lstrip() != "private":
                raise self._invalid_metadata(
                    f"{import_name!r} is invalid for {{field}}; "
                    "the only valid option is 'private'"
                )
        return value

    _process_import_namespaces = _process_import_names


class Metadata:
    """Representation of distribution metadata.

    Compared to :class:`RawMetadata`, this class provides objects representing
    metadata fields instead of only using built-in types. Any invalid metadata
    will cause :exc:`InvalidMetadata` to be raised (with a
    :py:attr:`~BaseException.__cause__` attribute as appropriate).
    """

    _raw: RawMetadata






















































































    metadata_version: _Validator[_MetadataVersion] = _Validator()
    """:external:ref:`core-metadata-metadata-version`
    (required; validated to be a valid metadata version)"""
    # `name` is not normalized/typed to NormalizedName so as to provide access to
    # the original/raw name.
    name: _Validator[str] = _Validator()
    """:external:ref:`core-metadata-name`
    (required; validated using :func:`~packaging.utils.canonicalize_name` and its
    *validate* parameter)"""
    version: _Validator[version_module.Version] = _Validator()
    """:external:ref:`core-metadata-version` (required)"""
    dynamic: _Validator[list[str] | None] = _Validator(
        added="2.2",
    )
    """:external:ref:`core-metadata-dynamic`
    (validated against core metadata field names and lowercased)"""
    platforms: _Validator[list[str] | None] = _Validator()
    """:external:ref:`core-metadata-platform`"""
    supported_platforms: _Validator[list[str] | None] = _Validator(added="1.1")
    """:external:ref:`core-metadata-supported-platform`"""
    summary: _Validator[str | None] = _Validator()
    """:external:ref:`core-metadata-summary` (validated to contain no newlines)"""
    description: _Validator[str | None] = _Validator()  # TODO 2.1: can be in body
    """:external:ref:`core-metadata-description`"""
    description_content_type: _Validator[str | None] = _Validator(added="2.1")
    """:external:ref:`core-metadata-description-content-type` (validated)"""
    keywords: _Validator[list[str] | None] = _Validator()
    """:external:ref:`core-metadata-keywords`"""
    home_page: _Validator[str | None] = _Validator()
    """:external:ref:`core-metadata-home-page`"""
    download_url: _Validator[str | None] = _Validator(added="1.1")
    """:external:ref:`core-metadata-download-url`"""
    author: _Validator[str | None] = _Validator()
    """:external:ref:`core-metadata-author`"""
    author_email: _Validator[str | None] = _Validator()
    """:external:ref:`core-metadata-author-email`"""
    maintainer: _Validator[str | None] = _Validator(added="1.2")
    """:external:ref:`core-metadata-maintainer`"""
    maintainer_email: _Validator[str | None] = _Validator(added="1.2")
    """:external:ref:`core-metadata-maintainer-email`"""
    license: _Validator[str | None] = _Validator()
    """:external:ref:`core-metadata-license`"""
    license_expression: _Validator[NormalizedLicenseExpression | None] = _Validator(
        added="2.4"
    )
    """:external:ref:`core-metadata-license-expression`"""
    license_files: _Validator[list[str] | None] = _Validator(added="2.4")
    """:external:ref:`core-metadata-license-file`"""
    classifiers: _Validator[list[str] | None] = _Validator(added="1.1")
    """:external:ref:`core-metadata-classifier`"""
    requires_dist: _Validator[list[requirements.Requirement] | None] = _Validator(
        added="1.2"
    )
    """:external:ref:`core-metadata-requires-dist`"""
    requires_python: _Validator[specifiers.SpecifierSet | None] = _Validator(
        added="1.2"
    )
    """:external:ref:`core-metadata-requires-python`"""
    # Because `Requires-External` allows for non-PEP 440 version specifiers, we
    # don't do any processing on the values.
    requires_external: _Validator[list[str] | None] = _Validator(added="1.2")
    """:external:ref:`core-metadata-requires-external`"""
    project_urls: _Validator[dict[str, str] | None] = _Validator(added="1.2")
    """:external:ref:`core-metadata-project-url`"""
    # PEP 685 lets us raise an error if an extra doesn't pass `Name` validation
    # regardless of metadata version.
    provides_extra: _Validator[list[utils.NormalizedName] | None] = _Validator(
        added="2.1",
    )
    """:external:ref:`core-metadata-provides-extra`"""
    provides_dist: _Validator[list[str] | None] = _Validator(added="1.2")
    """:external:ref:`core-metadata-provides-dist`"""
    obsoletes_dist: _Validator[list[str] | None] = _Validator(added="1.2")
    """:external:ref:`core-metadata-obsoletes-dist`"""
    import_names: _Validator[list[str] | None] = _Validator(added="2.5")
    """:external:ref:`core-metadata-import-name`"""
    import_namespaces: _Validator[list[str] | None] = _Validator(added="2.5")
    """:external:ref:`core-metadata-import-namespace`"""
    requires: _Validator[list[str] | None] = _Validator(added="1.1")
    """``Requires`` (deprecated)"""
    provides: _Validator[list[str] | None] = _Validator(added="1.1")
    """``Provides`` (deprecated)"""
    obsoletes: _Validator[list[str] | None] = _Validator(added="1.1")
    """``Obsoletes`` (deprecated)"""

    @classmethod
    def from_raw(cls, data: RawMetadata, *, validate: bool = True) -> Metadata:
        ins = cls.__new__(cls)
        ins._raw = data.copy()  # type: ignore[assignment]

        if validate:
            exceptions: list[InvalidMetadata] = []
            for attr_name in dir(cls):
                attr = getattr(cls, attr_name, None)
                if not isinstance(attr, _Validator):
                    continue
                try:
                    getattr(ins, attr_name)
                except InvalidMetadata as e:
                    exceptions.append(e)
            if exceptions:
                raise ExceptionGroup("invalid metadata", exceptions)

        return ins

    @classmethod
    def from_email(
        cls, data: bytes | str, *, validate: bool = True
    ) -> Metadata:
        raw, unparsed = parse_email(data)
        exceptions: list[InvalidMetadata] = []

        if validate and unparsed:
            for field, values in unparsed.items():
                if field in _EMAIL_TO_RAW_MAPPING.values():
                    raw_name = _RAW_TO_EMAIL_MAPPING.get(field, field)
                else:
                    raw_name = field
                exceptions.append(
                    InvalidMetadata(raw_name, f"{raw_name} is invalid")
                )

        try:
            meta = cls.from_raw(raw, validate=validate)
        except ExceptionGroup as eg:
            exceptions.extend(eg.exceptions)  # type: ignore[arg-type]

        if exceptions:
            raise ExceptionGroup("invalid metadata", exceptions)

        if not validate or not unparsed:
            meta = cls.from_raw(raw, validate=validate)

        return meta

    def as_rfc822(self) -> RFC822Message:
        msg = RFC822Message()
        self._write_metadata(msg)
        return msg

    def _write_metadata(self, msg: RFC822Message) -> None:
        for attr_name in type(self).__dict__:
            attr = getattr(type(self), attr_name, None)
            if not isinstance(attr, _Validator):
                continue
            try:
                value = getattr(self, attr_name)
            except InvalidMetadata:
                continue

            if value is None:
                continue

            header_name = _RAW_TO_EMAIL_MAPPING[attr_name]

            if attr_name == "description":
                msg.set_payload(value + "\n", charset="utf-8")
            elif attr_name == "keywords":
                msg[header_name] = ",".join(value)
            elif attr_name == "project_urls":
                for label, url in value.items():
                    msg[header_name] = f"{label}, {url}"
            elif isinstance(value, list):
                if attr_name in {"import_names", "import_namespaces"} and len(value) == 0:
                    msg[header_name] = ""
                else:
                    for item in value:
                        msg[header_name] = str(item)
            elif isinstance(value, dict):
                for k, v in value.items():
                    msg[header_name] = f"{k}, {v}"
            else:
                msg[header_name] = str(value)

























