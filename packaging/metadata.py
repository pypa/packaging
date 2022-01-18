# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.

import dataclasses
import math
import sys
import textwrap
from email import message_from_bytes
from email.contentmanager import raw_data_manager
from email.headerregistry import Address, AddressHeader
from email.message import EmailMessage
from email.policy import EmailPolicy, Policy
from functools import reduce
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
    NamedTuple,
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


class EmailAddress(NamedTuple):
    """Named tuple representing an email address.
    For values without a display name use ``EmailAddress(None, "your@email.com")``
    """

    display_name: Union[str, None]
    value: str

    def __str__(self) -> str:
        return str(Address(self.display_name or "", addr_spec=self.value))


@dataclasses.dataclass(frozen=True)
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
    author_email: Collection[EmailAddress] = ()
    license: str = ""
    # license_file: Collection[str] = ()  # not standard yet
    # 1.1
    supported_platform: Collection[str] = ()
    download_url: str = ""
    classifier: Collection[str] = ()
    # 1.2
    maintainer: str = ""
    maintainer_email: Collection[EmailAddress] = ()
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

    def __post_init__(self) -> None:
        """Perform required data conversions, validations, and ensure immutability"""

        _should_be_set = (self._MULTIPLE_USE | {"keywords"}) - {"project_url"}

        for field in self._fields():
            value = getattr(self, field)
            if field.endswith("dist"):
                reqs = (self._convert_single_req(v) for v in value)
                _setattr(self, field, frozenset(reqs))
            elif field.endswith("email"):
                emails = self._convert_emails(value)
                _setattr(self, field, frozenset(emails))
            elif field in _should_be_set:
                _setattr(self, field, frozenset(value))
            elif field in {"description", "summary"}:
                _setattr(self, field, value.strip())

        urls = self.project_url
        if not isinstance(urls, Mapping) and isinstance(urls, Iterable):
            urls = {}
            for url in cast(Iterable[str], self.project_url):
                key, _, value = url.partition(",")
                urls[key.strip()] = value.strip()
        _setattr(self, "project_url", urls)

        # Dataclasses don't enforce data types at runtime.
        if not isinstance(self.requires_python, SpecifierSet):
            requires_python = self._parse_requires_python(self.requires_python)
            _setattr(self, "requires_python", requires_python)
        if self.version and not isinstance(self.version, Version):
            _setattr(self, "version", Version(self.version))

        if self.dynamic:
            values = (_normalize_field_name_for_dynamic(f) for f in self.dynamic)
            dynamic = frozenset(v for v in values if self._validate_dynamic(v))
            _setattr(self, "dynamic", dynamic)

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
    def _read_pkg_info(cls, pkg_info: bytes) -> Dict[str, Any]:
        """Parse PKG-INFO data."""

        msg = message_from_bytes(pkg_info, EmailMessage, policy=cls._PARSING_POLICY)
        info = cast(EmailMessage, msg)

        attrs: Dict[str, Any] = {}
        for key in info.keys():
            field = key.lower().replace("-", "_")
            if field in cls._UPDATES:
                field = cls._UPDATES[field]

            value = str(info.get(key))  # email.header.Header.__str__ handles encoding

            if field == "keywords":
                attrs[field] = " ".join(value.splitlines()).split(",")
            elif field == "description":
                attrs[field] = cls._unescape_description(value)
            elif field.endswith("email"):
                attrs[field] = cls._parse_emails(value)
            elif field in cls._MULTIPLE_USE:
                attrs[field] = (str(v) for v in info.get_all(key))
            elif field in cls._fields():
                attrs[field] = value

        if "description" not in attrs:
            attrs["description"] = info.get_content(content_manager=raw_data_manager)

        return attrs

    @classmethod
    def from_pkg_info(cls: Type[T], pkg_info: bytes) -> T:
        """Parse PKG-INFO data."""

        return cls(**cls._read_pkg_info(pkg_info))

    @classmethod
    def from_dist_info_metadata(cls: Type[T], metadata_source: bytes) -> T:
        """Parse METADATA data."""

        attrs = cls._read_pkg_info(metadata_source)

        if "dynamic" in attrs:
            raise DynamicNotAllowed(attrs["dynamic"])

        missing_fields = [k for k in cls._MANDATORY if not attrs.get(k)]
        if missing_fields:
            raise MissingRequiredFields(missing_fields)

        return cls(**attrs)

    def to_pkg_info(self) -> bytes:
        """Generate PKG-INFO data."""

        info = EmailMessage(self._PARSING_POLICY)
        info.add_header("Metadata-Version", self.metadata_version)
        # Use `sorted` in collections to improve reproducibility
        for field in self._fields():
            value = getattr(self, field)
            if not value:
                continue
            key = self._canonical_field(field)
            if field == "keywords":
                info.add_header(key, ",".join(sorted(value)))
            elif field.endswith("email"):
                _emails = (str(v) for v in value)
                emails = ", ".join(sorted(v for v in _emails if v))
                info.add_header(key, emails)
            elif field == "project_url":
                for kind in sorted(value):
                    info.add_header(key, f"{kind}, {value[kind]}")
            elif field == "description":
                info.set_content(value, content_manager=raw_data_manager)
            elif field in self._MULTIPLE_USE:
                for single_value in sorted(str(v) for v in value):
                    info.add_header(key, single_value)
            else:
                info.add_header(key, str(value))

        return info.as_bytes()

    def to_dist_info_metadata(self) -> bytes:
        """Generate METADATA data."""
        if self.dynamic:
            raise DynamicNotAllowed(self.dynamic)
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
    def _convert_single_req(cls, value: Union[Requirement, str]) -> Requirement:
        return value if isinstance(value, Requirement) else cls._parse_req(value)

    @classmethod
    def _convert_emails(
        cls, value: Collection[Union[str, Tuple[str, str]]]
    ) -> Iterator[EmailAddress]:
        for email in value:
            if isinstance(email, str):
                yield from cls._parse_emails(email)
            elif isinstance(email, tuple) and email[1]:
                yield EmailAddress(email[0], email[1])

    @classmethod
    def _parse_emails(cls, value: str) -> Iterator[EmailAddress]:
        singleline = " ".join(value.splitlines())
        if singleline.strip() == "UNKNOWN":
            return
        address_list = AddressHeader.value_parser(singleline)
        for mailbox in address_list.all_mailboxes:
            yield EmailAddress(mailbox.display_name, mailbox.addr_spec)

    @classmethod
    def _unescape_description(cls, content: str) -> str:
        """Reverse RFC-822 escaping by removing leading whitespaces from content."""
        lines = content.splitlines()
        if not lines:
            return ""

        first_line = lines[0].lstrip()
        text = textwrap.dedent("\n".join(lines[1:]))
        other_lines = (line.lstrip("|") for line in text.splitlines())
        return "\n".join(chain([first_line], other_lines))

    def _validate_dynamic(self, normalized: str) -> bool:
        field = normalized.lower().replace("-", "_")
        if not hasattr(self, field):
            raise InvalidCoreMetadataField(normalized)
        if field in self._NOT_DYNAMIC:
            raise InvalidDynamicField(normalized)
        if getattr(self, field):
            raise StaticFieldCannotBeDynamic(normalized)
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
