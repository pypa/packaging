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
            return f"ExceptionGroup({self.message!r}, {self.exceptions!r})"









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
    return [k.strip() for k in data.split(",") if k.strip()]


def _parse_project_urls(data: list[str]) -> dict[str, str]:
    urls: dict[str, str] = {}
    for pair in data:
        label, _, url = (s.strip() for s in pair.partition(","))
        if label in urls:
            raise KeyError("duplicate labels in project urls")
        urls[label] = url
    return urls
































































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
        size = len(name) + 2
        value = value.replace("\n", "\n" + " " * size)
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
        self, unixfrom: bool = False, policy: email.policy.Policy | None = None
    ) -> bytes:
        return self.as_string(unixfrom=unixfrom, policy=policy).encode("utf-8")


def _get_payload(msg: email.message.Message, source: bytes | str) -> str:
    if isinstance(source, str):
        payload = msg.get_payload()
        assert isinstance(payload, str)
        return payload
    else:
        bpayload = msg.get_payload(decode=True)
        assert isinstance(bpayload, bytes)
        try:
            return bpayload.decode("utf8", "strict")
        except UnicodeDecodeError as exc:
            raise ValueError("payload in an invalid encoding") from exc


def parse_email(
    data: bytes | str,
) -> tuple[RawMetadata, dict[str, list[Any]]]:
    raw: dict[str, str | list[str] | dict[str, str]] = {}
    unparsed: dict[str, list[Any]] = {}

    if isinstance(data, str):
        parsed = email.parser.Parser(policy=email.policy.compat32).parsestr(data)
    else:
        parsed = email.parser.BytesParser(
            policy=email.policy.compat32
        ).parsebytes(data)

    for name_with_case in frozenset(parsed.keys()):
        name = name_with_case.lower()

        headers = parsed.get_all(name) or []

        value: list[str] = []
        valid_encoding = True
        for h in headers:
            assert isinstance(h, (email.header.Header, str))

            if isinstance(h, email.header.Header):
                chunks: list[tuple[bytes, str | None]] = []
                for binary, _encoding in email.header.decode_header(h):
                    try:
                        binary.decode("utf8", "strict")
                    except UnicodeDecodeError:
                        encoding: str | None = "latin1"
                        valid_encoding = False
                    else:
                        encoding = "utf8"
                    chunks.append((binary, encoding))

                value.append(str(email.header.make_header(chunks)))
            else:
                value.append(h)

        if not valid_encoding:
            unparsed[name] = value
            continue

        raw_name = _EMAIL_TO_RAW_MAPPING.get(name)
        if raw_name is None:
            unparsed[name] = value
            continue

        if raw_name in _STRING_FIELDS and len(value) == 1:
            raw[raw_name] = value[0]
        elif raw_name == "import_names" and value == [""]:
            raw[raw_name] = []
        elif raw_name == "import_namespaces" and value == [""]:
            raw[raw_name] = []
        elif raw_name in _LIST_FIELDS:
            raw[raw_name] = value
        elif raw_name == "keywords" and len(value) == 1:
            raw[raw_name] = _parse_keywords(value[0])
        elif raw_name == "project_urls":
            try:
                raw[raw_name] = _parse_project_urls(value)
            except KeyError:
                unparsed[name] = value
        else:
            unparsed[name] = value

    try:
        payload = _get_payload(parsed, data)
    except ValueError:
        unparsed.setdefault("description", []).append(
            parsed.get_payload(decode=isinstance(data, bytes))
        )
    else:
        if payload:
            if "description" in raw:
                description_header = cast("str", raw.pop("description"))
                unparsed.setdefault("description", []).extend(
                    [description_header, payload]
                )
            elif "description" in unparsed:
                unparsed["description"].append(payload)
            else:
                raw["description"] = payload

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

    def __get__(self, instance: Metadata | None, _owner: type[Metadata]) -> T:
        if instance is None:
            return self  # type: ignore[return-value]

        try:
            return cast(T, instance.__dict__[self.name])
        except KeyError:
            pass

        raw_value = instance._raw.get(self.name, _NOT_FOUND)
        if raw_value is _NOT_FOUND:
            if self.name in _REQUIRED_ATTRS:
                raise InvalidMetadata(
                    self.raw_name,
                    f"{self.raw_name} is a required field",
                )
            instance.__dict__[self.name] = None
            return cast(T, None)

        try:
            processor: Callable[[Any], T] | None = getattr(
                self, f"_process_{self.name}", None
            )
            if processor is not None:
                value = processor(raw_value)
            else:
                value = raw_value
        except InvalidMetadata:
            raise
        else:
            instance.__dict__[self.name] = value
            del instance._raw[self.name]  # type: ignore[misc]
            return value

    def _invalid_metadata(self, msg: str) -> InvalidMetadata:
        return InvalidMetadata(self.raw_name, msg.replace("{field}", self.raw_name))

    def _process_metadata_version(self, value: str) -> _MetadataVersion:
        if value not in _VALID_METADATA_VERSIONS:
            raise InvalidMetadata(
                "metadata-version",
                f"Unknown metadata version: {value!r}",
            )
        return cast(_MetadataVersion, value)

    def _process_name(self, value: str) -> str:
        if not value:
            raise InvalidMetadata("name", "name is a required field")
        try:
            utils.canonicalize_name(value, validate=True)
        except utils.InvalidName as e:
            raise InvalidMetadata("name", str(e)) from e
        return value

    def _process_version(self, value: str) -> version_module.Version:
        if not value:
            raise InvalidMetadata("version", "version is a required field")
        try:
            return version_module.Version(value)
        except version_module.InvalidVersion as e:
            raise InvalidMetadata("version", str(e)) from e

    def _process_summary(self, value: str) -> str:
        if "\n" in value:
            raise InvalidMetadata(
                "summary", "summary must not contain newlines"
            )
        return value

    def _process_description_content_type(self, value: str) -> str:
        content_types = {"text/plain", "text/x-rst", "text/markdown"}
        message = email.message.EmailMessage()
        message["content-type"] = value

        content_type, parameters = (
            message.get_content_type().lower(),
            message["content-type"].params,
        )
        if content_type not in content_types or content_type not in value.lower():
            raise self._invalid_metadata(
                f"{{field}} must be one of {list(content_types)}, not {value!r}"
            )

        charset = parameters.get("charset", "UTF-8")
        if charset != "UTF-8":
            raise self._invalid_metadata(
                f"{{field}} can only specify the UTF-8 charset, not {charset!r}"
            )

        markdown_variants = {"GFM", "CommonMark"}
        variant = parameters.get("variant", "GFM")
        if content_type == "text/markdown" and variant not in markdown_variants:
            raise self._invalid_metadata(
                f"valid Markdown variants for {{field}} are {list(markdown_variants)}, "
                f"not {variant!r}",
            )
        return value

    def _process_dynamic(self, value: list[str]) -> list[str]:
        dynamic_fields = list(map(str.lower, value))
        for dynamic_field in dynamic_fields:
            if dynamic_field in {"name", "version", "metadata-version"}:
                raise self._invalid_metadata(
                    f"{dynamic_field!r} is not allowed as a dynamic field"
                )
            elif dynamic_field not in _EMAIL_TO_RAW_MAPPING:
                raise self._invalid_metadata(
                    f"{dynamic_field!r} is not a valid dynamic field"
                )
        return dynamic_fields

    def _process_license_expression(
        self, value: str
    ) -> NormalizedLicenseExpression:
        try:
            return licenses.canonicalize_license_expression(value)
        except ValueError as e:
            raise InvalidMetadata(
                "license-expression", str(e)
            ) from e

    def _process_license_files(self, value: list[str]) -> list[str]:
        for path in value:
            if ".." in path:
                raise self._invalid_metadata(
                    f"Invalid license file path: {path!r} — contains '..'"
                )
            if "*" in path:
                raise self._invalid_metadata(
                    f"Invalid license file path: {path!r} — contains '*'"
                )
            if "\\" in path:
                raise self._invalid_metadata(
                    f"Invalid license file path: {path!r} — contains backslash"
                )
            if pathlib.PurePosixPath(path).is_absolute() or pathlib.PureWindowsPath(
                path
            ).is_absolute():
                raise self._invalid_metadata(
                    f"Invalid license file path: {path!r} — is absolute"
                )
        return value

    def _process_provides_extra(
        self, value: list[str]
    ) -> list[utils.NormalizedName]:
        result: list[utils.NormalizedName] = []
        for extra in value:
            try:
                result.append(utils.canonicalize_name(extra, validate=True))
            except utils.InvalidName as e:
                raise InvalidMetadata(
                    "provides-extra", str(e)
                ) from e
        return result

    def _process_requires_dist(
        self, value: list[str]
    ) -> list[requirements.Requirement]:
        result: list[requirements.Requirement] = []
        for item in value:
            try:
                result.append(requirements.Requirement(item))
            except requirements.InvalidRequirement as e:
                raise InvalidMetadata(
                    "requires-dist", str(e)
                ) from e
        return result

    def _process_requires_python(
        self, value: str
    ) -> specifiers.SpecifierSet:
        try:
            return specifiers.SpecifierSet(value)
        except specifiers.InvalidSpecifier as e:
            raise InvalidMetadata(
                "requires-python", str(e)
            ) from e



























































































































































































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
        ins._unparsed: dict[str, list[Any]] = {}

        if validate:
            exceptions: list[Exception] = []

            for attr_name, descriptor in _get_validators(cls):
                try:
                    getattr(ins, attr_name)
                except InvalidMetadata as e:
                    exceptions.append(e)

            try:
                mv = ins.__dict__.get("metadata_version")
                if mv is not None:
                    for attr_name, descriptor in _get_validators(cls):
                        if attr_name in _REQUIRED_ATTRS:
                            continue
                        if attr_name in ins.__dict__ and ins.__dict__[attr_name] is not None:
                            if _VALID_METADATA_VERSIONS.index(descriptor.added) > _VALID_METADATA_VERSIONS.index(mv):
                                exceptions.append(
                                    InvalidMetadata(
                                        descriptor.raw_name,
                                        f"{descriptor.raw_name} was added in metadata version {descriptor.added}, not {mv}",
                                    )
                                )
            except (ValueError, InvalidMetadata):
                pass

            leftover = set(ins._raw.keys())
            for attr_name, _ in _get_validators(cls):
                leftover.discard(attr_name)
            for field_name in leftover:
                exceptions.append(
                    InvalidMetadata(
                        field_name,
                        f"unrecognized field: {field_name!r}",
                    )
                )

            if exceptions:
                raise ExceptionGroup("invalid metadata", exceptions)

        return ins

    @classmethod
    def from_email(
        cls, data: bytes | str, *, validate: bool = True
    ) -> Metadata:
        raw, unparsed = parse_email(data)

        if validate:
            exceptions: list[Exception] = []
            for unparsed_key in unparsed:
                if unparsed_key in _EMAIL_TO_RAW_MAPPING:
                    message = f"{unparsed_key!r} has invalid data"
                else:
                    message = f"unrecognized field: {unparsed_key!r}"
                exceptions.append(InvalidMetadata(unparsed_key, message))
            if exceptions:
                raise ExceptionGroup("unparsed", exceptions)

        try:
            return cls.from_raw(raw, validate=validate)
        except ExceptionGroup as exc_group:
            raise ExceptionGroup(
                "invalid or unparsed metadata", exc_group.exceptions
            ) from None

    def as_rfc822(self) -> RFC822Message:
        message = RFC822Message()
        self._write_metadata(message)
        return message

    def _write_metadata(self, message: RFC822Message) -> None:
        for name, validator in self.__class__.__dict__.items():
            if isinstance(validator, _Validator) and name != "description":
                value = getattr(self, name)
                email_name = _RAW_TO_EMAIL_MAPPING[name]
                if value is not None:
                    if email_name == "project-url":
                        for label, url in value.items():
                            message[email_name] = f"{label}, {url}"
                    elif email_name == "keywords":
                        message[email_name] = ",".join(value)
                    elif email_name == "import-name" and value == []:
                        message[email_name] = ""
                    elif isinstance(value, list):
                        for item in value:
                            message[email_name] = str(item)
                    else:
                        message[email_name] = str(value)

        if self.description is not None:
            message.set_payload(self.description)


def _get_validators(cls: type[Metadata]) -> list[tuple[str, _Validator[Any]]]:
    result = []
    for attr_name in dir(cls):
        obj = getattr(cls, attr_name, None)
        if isinstance(obj, _Validator):
            result.append((attr_name, obj))
    return result



























