# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.

import dataclasses
import math
import sys
from email import message_from_bytes
from email.headerregistry import Address, AddressHeader
from email.message import EmailMessage
from email.policy import EmailPolicy, Policy
from functools import reduce
from inspect import cleandoc
from itertools import chain
from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
    Collection,
    Dict,
    Iterable,
    Iterator,
    Mapping,
    Set,
    Tuple,
    Type,
    TypeVar,
    Union,
    cast,
)

from .requirements import InvalidRequirement, Requirement
from .specifiers import SpecifierSet
from .version import Version

T = TypeVar("T", bound="CoreMetadata")
A = TypeVar("A")
B = TypeVar("B")

if sys.version_info[:2] >= (3, 8) and TYPE_CHECKING:  # pragma: no cover
    from typing import Literal

    NormalizedDynamicFields = Literal[
        "platform",
        "summary",
        "description",
        "keywords",
        "home-page",
        "author",
        "author-email",
        "license",
        "supported-platform",
        "download-url",
        "classifier",
        "maintainer",
        "maintainer-email",
        "requires-dist",
        "requires-python",
        "requires-external",
        "project-url",
        "provides-extra",
        "provides-dist",
        "obsoletes-dist",
        "description-content-type",
    ]
else:
    NormalizedDynamicFields = str


def _normalize_field_name_for_dynamic(field: str) -> NormalizedDynamicFields:
    """Normalize a metadata field name that is acceptable in `dynamic`.

    The field name will be normalized to lower-case. JSON field names are
    also acceptable and will be translated accordingly.

    """
    return cast(NormalizedDynamicFields, field.lower().replace("_", "-"))


# Bypass frozen dataclass for __post_init__, this approach is documented in:
# https://docs.python.org/3/library/dataclasses.html#frozen-instances
_setattr = object.__setattr__


# In the following we use `frozen` to prevent inconsistencies, specially with `dynamic`.
# Comparison is disabled because currently `Requirement` objects are
# unhashable/not-comparable.


@dataclasses.dataclass(frozen=True, eq=False)
class CoreMetadata:
    """
    Core metadata for Python packages, represented as an immutable
    :obj:`dataclass <dataclasses>`.

    Specification: https://packaging.python.org/en/latest/specifications/core-metadata/

    Attribute names follow :pep:`PEP 566's JSON guidelines
    <566#json-compatible-metadata>`.
    """

    # 1.0
    name: str
    version: Union[Version, None] = None
    platform: Collection[str] = ()
    summary: str = ""
    description: str = ""
    keywords: Collection[str] = ()
    home_page: str = ""
    author: str = ""
    author_email: Collection[Tuple[Union[str, None], str]] = ()
    license: str = ""
    # license_file: Collection[str] = ()  # not standard yet
    # 1.1
    supported_platform: Collection[str] = ()
    download_url: str = ""
    classifier: Collection[str] = ()
    # 1.2
    maintainer: str = ""
    maintainer_email: Collection[Tuple[Union[str, None], str]] = ()
    requires_dist: Collection[Requirement] = ()
    requires_python: SpecifierSet = dataclasses.field(default_factory=SpecifierSet)
    requires_external: Collection[str] = ()
    project_url: Mapping[str, str] = dataclasses.field(default_factory=dict)
    provides_extra: Collection[str] = ()
    provides_dist: Collection[Requirement] = ()
    obsoletes_dist: Collection[Requirement] = ()
    # 2.1
    description_content_type: str = ""
    # 2.2
    dynamic: Collection[NormalizedDynamicFields] = ()

    @property
    def metadata_version(self) -> str:
        """
        The data structure is always compatible with the latest approved
        version of the spec, even when parsing files that use previous versions.
        """
        return "2.2"

    @classmethod
    def _fields(cls) -> Collection[str]:
        return [f.name for f in dataclasses.fields(cls)]

    @classmethod
    def _process_attrs(
        cls, attrs: Iterable[Tuple[str, Any]]
    ) -> Iterable[Tuple[str, Any]]:
        """Transform input data to the matching attribute types."""

        _as_set = (cls._MULTIPLE_USE | {"keywords"}) - {"project_url"}
        _available_fields = cls._fields()

        for field, value in attrs:
            if field == "version":
                yield ("version", Version(value))
            elif field == "keywords":
                yield (field, frozenset(value.split(",")))
            elif field == "requires_python":
                yield (field, cls._parse_requires_python(value))
            elif field == "project_url":
                urls = {}
                for url in value:
                    key, _, value = url.partition(",")
                    urls[key.strip()] = value.strip()
                yield (field, urls)
            elif field == "dynamic":
                values = (_normalize_field_name_for_dynamic(f) for f in value)
                yield (field, frozenset(values))
            elif field.endswith("email"):
                yield (field, frozenset(cls._parse_emails(value.strip())))
            elif field.endswith("dist"):
                yield (field, frozenset(cls._parse_req(v) for v in value))
            elif field in _as_set:
                yield (field, frozenset(value))
            elif field in _available_fields:
                yield (field, value)

    @classmethod
    def _parse_pkg_info(cls, pkg_info: bytes) -> Iterable[Tuple[str, Any]]:
        """Parse PKG-INFO data."""

        msg = message_from_bytes(pkg_info, EmailMessage, policy=cls._PARSING_POLICY)
        info = cast(EmailMessage, msg)
        has_description = False

        for key in info.keys():
            field = key.lower().replace("-", "_")
            if field in cls._UPDATES:
                field = cls._UPDATES[field]

            value = str(info.get(key))  # email.header.Header.__str__ handles encoding

            if field in {"keywords", "summary"} or field.endswith("email"):
                yield (field, cls._ensure_single_line(value))
            elif field == "description":
                has_description = True
                yield (field, cls._unescape_description(value))
            elif field in cls._MULTIPLE_USE:
                yield (field, (str(v) for v in info.get_all(key)))
            else:
                yield (field, value)

        if not has_description:
            yield ("description", str(info.get_payload(decode=True), "utf-8"))

    @classmethod
    def from_pkg_info(cls: Type[T], pkg_info: bytes) -> T:
        """Parse PKG-INFO data."""

        attrs = cls._process_attrs(cls._parse_pkg_info(pkg_info))
        obj = cls(**dict(attrs))
        obj._validate_dynamic()
        return obj

    @classmethod
    def from_dist_info_metadata(cls: Type[T], metadata_source: bytes) -> T:
        """Parse METADATA data."""

        obj = cls.from_pkg_info(metadata_source)
        obj._validate_final_metadata()
        return obj

    def to_pkg_info(self) -> bytes:
        """Generate PKG-INFO data."""

        self._validate_dynamic()

        info = EmailMessage(self._PARSING_POLICY)
        info.add_header("Metadata-Version", self.metadata_version)
        # Use `sorted` in collections to improve reproducibility
        for field in self._fields():
            value = getattr(self, field)
            if not value:
                continue
            key = self._canonical_field(field)
            if field in "keywords":
                info.add_header(key, ",".join(sorted(value)))
            elif field.endswith("email"):
                _emails = (self._serialize_email(v) for v in value if any(v))
                emails = ", ".join(sorted(v for v in _emails if v))
                if emails:
                    info.add_header(key, emails)
            elif field == "project_url":
                for kind in sorted(value):
                    info.add_header(key, f"{kind}, {value[kind]}")
            elif field == "description":
                info.set_payload(bytes(value, "utf-8"))
            elif field in self._MULTIPLE_USE:
                for single_value in sorted(str(v) for v in value):
                    info.add_header(key, single_value)
            else:
                info.add_header(key, str(value))

        return info.as_bytes()

    def to_dist_info_metadata(self) -> bytes:
        """Generate METADATA data."""

        self._validate_final_metadata()
        return self.to_pkg_info()

    # --- Auxiliary Methods and Properties ---
    # Not part of the API, but can be overwritten by subclasses
    # (useful when providing a prof-of-concept for new PEPs)

    _MANDATORY: ClassVar[Set[str]] = {"name", "version"}
    _NOT_DYNAMIC: ClassVar[Set[str]] = {"metadata_version", "name", "dynamic"}
    _MULTIPLE_USE: ClassVar[Set[str]] = {
        "dynamic",
        "platform",
        "supported_platform",
        "classifier",
        "requires_dist",
        "requires_external",
        "project_url",
        "provides_extra",
        "provides_dist",
        "obsoletes_dist",
    }
    _UPDATES: ClassVar[Dict[str, str]] = {
        "requires": "requires_dist",  # PEP 314 => PEP 345
        "provides": "provides_dist",  # PEP 314 => PEP 345
        "obsoletes": "obsoletes_dist",  # PEP 314 => PEP 345
    }
    _PARSING_POLICY: ClassVar[Policy] = EmailPolicy(max_line_length=math.inf, utf8=True)

    @classmethod
    def _canonical_field(cls, field: str) -> str:
        words = _normalize_field_name_for_dynamic(field).split("-")
        ucfirst = "-".join(w[0].upper() + w[1:] for w in words)
        replacements = {"Url": "URL", "Email": "email", "Page": "page"}.items()
        return reduce(lambda acc, x: acc.replace(x[0], x[1]), replacements, ucfirst)

    @classmethod
    def _ensure_single_line(cls, value: str) -> str:
        """Existing distributions might include  metadata with fields such as 'keywords'
        or 'summary' showing up as multiline strings.
        """
        return " ".join(value.splitlines())

    @classmethod
    def _parse_requires_python(cls, value: str) -> SpecifierSet:
        if value and value[0].isnumeric():
            value = f"=={value}"
        return SpecifierSet(value)

    @classmethod
    def _parse_req(cls, value: str) -> Requirement:
        try:
            return Requirement(value)
        except InvalidRequirement:
            # Some old examples in PEPs use "()" around versions without an operator
            # e.g.: `Provides: xmltools (1.3)`
            name, _, rest = value.strip().partition("(")
            value = f"{name}(=={rest}"
            return Requirement(value)

    @classmethod
    def _parse_emails(cls, value: str) -> Iterator[Tuple[Union[str, None], str]]:
        if value == "UNKNOWN":
            return
        address_list = AddressHeader.value_parser(value)
        for mailbox in address_list.all_mailboxes:
            yield (mailbox.display_name, mailbox.addr_spec)

    @classmethod
    def _serialize_email(cls, value: Tuple[Union[str, None], str]) -> str:
        return str(Address(value[0] or "", addr_spec=value[1]))

    @classmethod
    def _unescape_description(cls, content: str) -> str:
        """Reverse RFC-822 escaping by removing leading whitespaces from content."""
        lines = cleandoc(content).splitlines()
        if not lines:
            return ""

        continuation = (line.lstrip("|") for line in lines[1:])
        return "\n".join(chain(lines[:1], continuation))

    def _validate_dynamic(self) -> bool:
        for normalized in self.dynamic:
            field = normalized.lower().replace("-", "_")
            if not hasattr(self, field):
                raise InvalidCoreMetadataField(normalized)
            if field in self._NOT_DYNAMIC:
                raise InvalidDynamicField(normalized)
            if getattr(self, field):
                raise StaticFieldCannotBeDynamic(normalized)
        return True

    def _validate_final_metadata(self) -> bool:
        if self.dynamic:
            raise DynamicNotAllowed(self.dynamic)

        missing_fields = [k for k in self._MANDATORY if not getattr(self, k)]
        if missing_fields:
            raise MissingRequiredFields(missing_fields)

        return True


class InvalidCoreMetadataField(ValueError):
    def __init__(self, field: str):
        super().__init__(f"{field!r} is not a valid core metadata field")


class InvalidDynamicField(ValueError):
    def __init__(self, field: str):
        super().__init__(f"{field!r} cannot be dynamic")


class StaticFieldCannotBeDynamic(ValueError):
    def __init__(self, field: str):
        super().__init__(f"{field!r} specified both dynamically and statically")


class DynamicNotAllowed(ValueError):
    def __init__(self, fields: Collection[str]):
        given = ", ".join(fields)
        super().__init__(f"Dynamic fields not allowed in this context (given: {given})")


class MissingRequiredFields(ValueError):
    def __init__(self, fields: Collection[str]):
        missing = ", ".join(fields)
        super().__init__(f"Required fields are missing: {missing}")
