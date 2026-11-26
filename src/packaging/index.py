from __future__ import annotations

import enum

# Make sure anyone importing this module just for the 'Accept' header values
# doesn't pay an unnecessary import penalty for other code.
__lazy_modules__ = {
    "contextlib",
    "datetime",
    "email.message",
    "hashlib",
    "html",
    "json",
    "urllib.parse",
    f"{__spec__.parent}.utils",
}
import contextlib
import datetime
import email.message
import functools
import hashlib
import html.parser  # HTMLParser used as a base class.
import json
import typing  # The `from ... import` forces an eager import.
import urllib.parse
from typing import (  # TypedDict is used as a base class.
    TYPE_CHECKING,
    Literal,
    TypedDict,
    TypeVar,
)

from . import specifiers, utils, version

if TYPE_CHECKING:
    import sys
    from collections.abc import Collection

    if sys.version_info >= (3, 13):
        from typing import TypeIs
    else:
        from typing_extensions import TypeIs

    from .utils import NormalizedName

__all__ = [
    "ACCEPT",
    "ACCEPT_HTML",
    "ACCEPT_JSON_V1",
    "IndexServerException",
    "InvalidContentType",
    "InvalidHTMLAttributeValue",
    "RawProjectDetails",
    "RawProjectDetailsFile",
    "RawProjectList",
    "parse_details",
    "parse_list",
]


def __dir__() -> list[str]:
    return __all__


class IndexServerException(Exception):
    """Base exception for all exceptions related to :mod:`packaging.index`."""


class InvalidContentType(ValueError, IndexServerException):
    """An invalid content type for an index server to respond with.

    Valid content types are encapsulated by :data:`ACCEPT`.
    """

    content_type: str

    def __init__(self, content_type: str) -> None:
        self.content_type = content_type
        super().__init__(f"Invalid content type: {content_type}")


class InvalidJSON(IndexServerException):
    """The structure of the JSON response from an index server was invalid.

    This can be caused by such things as missing keys that are required or the
    wrong types for values. Invalid values raise :exc:`InvalidData`.
    """


class InvalidData(IndexServerException):
    """Some value was invalid from an index server."""


class InvalidHTMLAttributeValue(ValueError, IndexServerException):
    """Invalid HTML tag value returned from an index server."""

    tag: str
    attr: str
    value: str

    def __init__(self, tag: str, attr: str, value: object) -> None:
        self.tag = tag
        self.attr = attr
        self.value = repr(value)
        super().__init__(f"invalid value for HTML <{tag} {self.attr}>: {self.value}")


ACCEPT_JSON_V1 = "application/vnd.pypi.simple.v1+json"
"""The HTTP ``Accept`` header value for version 1 of the JSON API."""
ACCEPT_HTML_VALUES = ["application/vnd.pypi.simple.v1+html", "text/html"]
"""The HTTP ``Accept`` values for HTML in order of preference."""
ACCEPT_HTML = f"{ACCEPT_HTML_VALUES[0]}, {ACCEPT_HTML_VALUES[1]};q=0.01"
"""The HTTP ``Accept`` header value for the HTML API."""
ACCEPT = ", ".join(
    [
        ACCEPT_JSON_V1,
        f"{ACCEPT_HTML_VALUES[0]};q=0.02",
        f"{ACCEPT_HTML_VALUES[1]};q=0.01",
    ]
)
"""The HTTP ``Accept`` header value for all supported response types with JSON prioritized."""  # noqa: E501


_ValueT = TypeVar("_ValueT", bound=int | str | bool | None)

_API_VERSION = Literal["1.0", "1.1", "1.3", "1.4"]
_API_VERSION_LIST: list[_API_VERSION] = ["1.0", "1.1", "1.3", "1.4"]


def _api_version_guard(version: object) -> TypeIs[_API_VERSION]:
    return isinstance(version, str) and version in _API_VERSION_LIST


class _ProjectData:
    _json_data: dict[object, object]
    _api_version: _API_VERSION

    def __init__(
        self,
        json_data: dict[object, object],
        api_version: _API_VERSION | None = None,
    ) -> None:
        """Store JSON data.

        If **api_version** is not given, it is read from
        ``json_data["meta"]["api-version"]``.
        """
        self._json_data = json_data
        if api_version is None:
            if (meta := json_data.get("meta")) is None:
                raise InvalidJSON("missing 'meta'")
            if not isinstance(meta, dict):
                raise InvalidJSON("expected 'meta' to be a dict")
            try:
                api_version = meta["api-version"]
            except KeyError as exc:
                raise InvalidJSON("missing 'api-version'") from exc

        if _api_version_guard(api_version):
            self._api_version = api_version
        else:
            raise InvalidData(f"API version {api_version!r} is unsupported")

    def _get(self, key: str, added_in: _API_VERSION) -> object:
        if _API_VERSION_LIST.index(self._api_version) < _API_VERSION_LIST.index(
            added_in
        ):
            return None
        try:
            return self._json_data[key]
        except KeyError:
            return None

    def _get_value(
        self, key: str, expect: type[_ValueT], added_in: _API_VERSION
    ) -> _ValueT | None:
        """Get a key from the JSON data and check its type is what's expected."""
        value = self._get(key, added_in)
        if value is None:
            return None
        elif not isinstance(value, expect):
            raise InvalidJSON(
                f"expected type {expect!r}, not {type(value)!r} for {key!r}"
            )
        return value

    def _get_list(
        self, key: str, expect_values: type[_ValueT], added_in: _API_VERSION
    ) -> list[_ValueT] | None:
        values = self._get(key, added_in)
        if values is None:
            return None
        elif not isinstance(values, list):
            raise InvalidJSON(f"expected a list for {key!r}")
        if not all(isinstance(v, expect_values) for v in values):
            raise InvalidJSON(f"expected a list of {expect_values!r} for {key!r}")
        return values

    def _get_dict(self, key: str, added_in: _API_VERSION) -> dict[str, str] | None:
        d = self._get(key, added_in)
        if d is None:
            return None
        elif not isinstance(d, dict):
            raise InvalidJSON(f"expected a dict for {key!r}")
        if not all(isinstance(k, str) and isinstance(v, str) for k, v in d.items()):
            raise InvalidJSON(
                f"expected dict of 'str' keys and 'str' values for {key!r}"
            )
        return d


class ProjectListDetails(_ProjectData):
    """Representation of a project's details as contained in a project list response.

    Data is lazily validated.
    """

    def __init__(
        self, json_data: dict[object, object], api_version: _API_VERSION
    ) -> None:
        super().__init__(json_data, api_version)

    @functools.cached_property
    def name(self) -> NormalizedName:
        "The normalized name of the project."
        name = self._get_value("name", str, "1.0")
        if name is None:
            raise InvalidJSON("missing 'name'")
        return utils.canonicalize_name(name)


class ProjectList(_ProjectData):
    """Representation of an index server's project list JSON response.

    Data is lazily validated.
    """

    def __init__(self, json_data: dict[object, object]) -> None:
        super().__init__(json_data)

    # 1.0
    @functools.cached_property
    def projects(self) -> list[ProjectListDetails]:
        """The list of projects hosted by the index."""
        projects = self._get("projects", "1.0")
        if not isinstance(projects, list):
            raise InvalidJSON("expected a list for 'projects'")
        if not all(isinstance(p, dict) for p in projects):
            raise InvalidJSON("expected dicts in 'projects'")
        return [ProjectListDetails(project, self._api_version) for project in projects]


def _append_url_suffix(url: str, suffix: str) -> str:
    parsed_url = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit(
        (
            parsed_url.scheme,
            parsed_url.netloc,
            parsed_url.path + suffix,
            parsed_url.query,
            "",
        )
    )


class ProjectDetailsFile(_ProjectData):
    """Representation of a project detail's file JSON response.

    Data is lazily validated.
    """

    _base_url: str

    def __init__(
        self, base_url: str, json_data: dict[object, object], api_version: _API_VERSION
    ) -> None:
        self._base_url = base_url
        super().__init__(json_data, api_version)

    @functools.cached_property
    def filename(self) -> str:
        """The filename of the file."""
        if (name := self._get_value("filename", str, "1.0")) is None:
            raise InvalidJSON("missing 'filename'")
        return name

    @functools.cached_property
    def url(self) -> str:
        """The URL for the file."""
        if (url := self._get_value("url", str, "1.0")) is None:
            raise InvalidJSON("missing 'url'")
        if not url.startswith(("http://", "https://")):
            url = urllib.parse.urljoin(self._base_url, url)
        return url

    @functools.cached_property
    def hashes(self) -> dict[str, str]:
        """The hashes of the file.

        The keys are for the hash algorithm and are lowercased. The values
        are the hash values.
        """
        raw_hashes = self._get_dict("hashes", "1.0")
        if raw_hashes is None:
            raise InvalidJSON("missing 'hashes'")
        return {k.lower(): v for k, v in raw_hashes.items()}

    @functools.cached_property
    def requires_python(self) -> specifiers.SpecifierSet | None:
        """The Python version requirement."""
        if raw := self._get_value("requires-python", str, "1.0"):
            return specifiers.SpecifierSet(raw)
        return None

    @functools.cached_property
    def gpg_sig(self) -> str | None:
        """The URL for the GPG signature."""
        if not self._get_value("gpg-sig", bool, "1.0"):
            return None
        return _append_url_suffix(self.url, ".asc")

    @functools.cached_property
    def yanked(self) -> tuple[bool, str]:
        """The yanked status of the file.

        Returns two-item tuple of whether the file is yanked and the reason.
        If the file is yanked but there is no given reason, the empty string is used.
        """
        yanked = self._get("yanked", "1.0")
        if yanked is None:
            return False, ""
        elif isinstance(yanked, str):
            return True, yanked
        elif isinstance(yanked, bool):
            return yanked, ""
        raise InvalidJSON(f"Expected 'yanked' to be bool or str, not {type(yanked)!r}")

    @functools.cached_property
    def core_metadata(self) -> tuple[str | None, dict[str, str]]:
        """The metadata for the file.

        Returns a tuple of the URL for the metadata file and hashes for the
        file. If there is no metadata specified to exist outside of the file,
        the URL will be ``None``. The hashes dictionary has its keys as
        lowercased hash algorithms and values as the hashes.
        """
        if (metadata := self._get("core-metadata", "1.0")) is None and (
            metadata := self._get("dist-info-metadata", "1.0")
        ) is None:
            return None, {}

        if not isinstance(metadata, (bool, dict)):
            raise InvalidJSON("Expected 'core-metadata' to be a bool or dict of hashes")
        if not metadata:
            return None, {}

        url = _append_url_suffix(self.url, ".metadata")
        if isinstance(metadata, dict):
            if not all(
                isinstance(k, str) and isinstance(v, str) for k, v in metadata.items()
            ):
                raise InvalidJSON(
                    "Expected hashes dict for 'core-metadata' to be strings for all "
                    "keys and values"
                )
            normalized_hashes = {k.lower(): v for k, v in metadata.items()}
            return url, normalized_hashes
        return url, {}

    @functools.cached_property
    def size(self) -> int | None:
        """The size of the file.

        Raises :exc:`InvalidData` if the size is negative.
        """
        if (size := self._get_value("size", int, "1.0")) is None:
            return None
        if size < 0:
            raise InvalidData("Expected 'size' to be non-negative")
        return size

    @functools.cached_property
    def upload_time(self) -> datetime.datetime | None:
        """The UTC upload time of the file.

        If the format does not match "%Y-%m-%dT%H:%M:%S.%fZ" or
        "%Y-%m-%dT%H:%M:%SZ", :exc:`InvalidData` is raised.
        """
        if (raw_datetime := self._get_value("upload-time", str, "1.1")) is None:
            return None
        elif len(raw_datetime) < len("yyyy-mm-ddThh:mm:ssZ") or len(raw_datetime) > len(
            "yyyy-mm-ddThh:mm:ss.ffffffZ"
        ):
            raise InvalidData("Invalid upload-time string length")

        if "." in raw_datetime:
            datetime_format = "%Y-%m-%dT%H:%M:%S.%fZ"
        else:
            datetime_format = "%Y-%m-%dT%H:%M:%SZ"
        try:
            return datetime.datetime.strptime(raw_datetime, datetime_format).replace(
                tzinfo=datetime.timezone.utc
            )
        except ValueError as exc:
            raise InvalidData("Invalid upload-time format") from exc

    @functools.cached_property
    def provenance(self) -> str | None:
        provenance = self._get("provenance", "1.3")
        if provenance is None:
            return None
        elif not isinstance(provenance, str):
            raise InvalidData(
                f"Expected a 'str' for provenance, not {type(provenance)}"
            )
        return provenance


class ProjectStatus(enum.Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    QUARANTINED = "quarantined"
    DEPRECATED = "deprecated"


class ProjectDetailsStatus(_ProjectData):
    def __init__(
        self, json_data: dict[object, object], api_version: _API_VERSION
    ) -> None:
        super().__init__(json_data, api_version)

    @functools.cached_property
    def status(self) -> ProjectStatus:
        if (status := self._get_value("status", str, "1.4")) is None:
            return ProjectStatus.ACTIVE
        return ProjectStatus(status)

    @functools.cached_property
    def reason(self) -> str | None:
        return self._get_value("reason", str, "1.4")


class ProjectDetails(_ProjectData):
    """Representation of a project's details JSON response."""

    _url: str

    def __init__(self, url: str, json_data: dict[object, object]) -> None:
        self._url = url
        super().__init__(json_data)

    @functools.cached_property
    def name(self) -> utils.NormalizedName:
        """The name of the project."""
        if (name := self._get_value("name", str, "1.0")) is None:
            raise InvalidJSON("Missing 'name'")
        return utils.canonicalize_name(name)

    @functools.cached_property
    def files(self) -> Collection[ProjectDetailsFile]:
        if (files := self._get("files", "1.0")) is None:
            raise InvalidJSON("Missing 'files'")
        if not isinstance(files, list):
            raise InvalidJSON("'files' is not a list")
        if not all(isinstance(f, dict) for f in files):
            raise InvalidJSON("Expected all values in 'files' to be dicts")
        return [ProjectDetailsFile(self._url, f, self._api_version) for f in files]

    @functools.cached_property
    def versions(self) -> frozenset[version.Version]:
        """Available versions for the project.

        If the response does not contain a precalculated list, it will be
        inferred from the filenames in :attr:`files`.
        """
        if (raw_versions := self._get_list("versions", str, "1.1")) is not None:
            try:
                return frozenset(map(version.Version, raw_versions))
            except version.InvalidVersion as exc:
                raise InvalidData("Invalid version from 'versions'") from exc

        versions = set()
        for file_details in self.files:
            filename = file_details.filename
            stem, _, suffix = filename.rpartition(".")
            match suffix:
                case "whl":
                    _, file_version, _ = stem.split("-", maxsplit=2)
                case "gz":
                    stem = stem.removesuffix(".tar")
                    _, _, file_version = stem.rpartition("-")
                case "zip":
                    _, _, file_version = stem.rpartition("-")
                case _:
                    raise InvalidData(f"Unknown file suffix {suffix!r}")
            try:
                versions.add(version.Version(file_version))
            except version.InvalidVersion as exc:
                raise InvalidData(f"Invalid version from filename {filename}") from exc
        return frozenset(versions)

    @functools.cached_property
    def project_status(self) -> ProjectDetailsStatus:
        if (raw_project_status := self._get("project-status", "1.4")) is None:
            return ProjectDetailsStatus({}, self._api_version)
        if not isinstance(raw_project_status, dict):
            raise InvalidJSON("expected a dict for 'project-status'")
        return ProjectDetailsStatus(
            {
                key: value
                for key, value in raw_project_status.items()
                if key in {"status", "reason"}
            },
            self._api_version,
        )


# Shared between list and detail responses.
# There is no API version 1.2 as it was introduced by PEP 708 which was rejected.
_RawProjectMeta = TypedDict(
    "_RawProjectMeta", {"api-version": Literal["1.0", "1.1", "1.3", "1.4"]}
)


class RawProjectList(TypedDict):
    """The :class:`~typing.TypedDict` JSON representation of the project list from an index server."""  # noqa: E501

    # 1.0
    meta: _RawProjectMeta
    projects: list[dict[Literal["name"], str]]


# This class only contains keys required across **all** API versions.
class _RawProjectDetailsFileRequired(TypedDict):
    # 1.0
    filename: str
    url: str
    hashes: dict[str, str]


# Since typing.NotRequired isn't available until 3.11, the functional
# TypedDict API doesn't allow subclassing, and there are keys which cannot be
# represented as attribute names, we need to split required and
# optional keys into separate classes that are then combined via
# multiple inheritance.
# Once Python 3.11 is the oldest supported version, the classes should be
# flattened to work with autodoc.
_RawProjectDetailsFileOptional = TypedDict(
    "_RawProjectDetailsFileOptional",
    {
        # 1.0
        "requires-python": str,
        "dist-info-metadata": bool | dict[str, str],  # Deprecated
        "gpg-sig": bool,
        "yanked": bool | str,
        # PEP 714
        "core-metadata": bool | dict[str, str],
        # 1.1
        "size": int,  # Mandatory for 1.1+, but not available for the HTML API.
        "upload-time": str,
        # 1.3
        "provenance": str | None,
    },
    total=False,
)


# Once Python 3.11 is the oldest supported version, the classes should be
# flattened to work with autodoc.
class RawProjectDetailsFile(
    _RawProjectDetailsFileRequired, _RawProjectDetailsFileOptional
):
    """The :class:`~typing.TypedDict` JSON representation of the objects contained in the "files" key of :class:`RawProjectDetails`.

    Do note that the 'size' key is not considered required; it doesn't exist in
    API version 1.0 nor is it supported by the HTML API.
    """  # noqa: E501


_PROJECT_STATUSES = Literal["active", "archived", "quarantined", "deprecated"]


class _RawProjectDetailsStatus(TypedDict, total=False):
    status: _PROJECT_STATUSES
    reason: str


# This class only contains keys required across **all** API versions.
class _RawProjectDetailsRequired(TypedDict):
    # 1.0
    meta: _RawProjectMeta
    name: str
    files: list[RawProjectDetailsFile]


_RawProjectDetailsOptional = TypedDict(
    "_RawProjectDetailsOptional",
    {
        # 1.1
        "versions": list[str],
        # 1.4
        "project-status": _RawProjectDetailsStatus,
    },
    total=False,
)


# Once Python 3.11 is the oldest supported version, the classes should be
# flattened to work with autodoc.
class RawProjectDetails(_RawProjectDetailsRequired, _RawProjectDetailsOptional):
    """The :class:`~typing.TypedDict` JSON representation of the project details from an index server.

    Due to supporting all possible API versions, some keys which are considered
    required in API versions post-1.0 are considered optional.
    """  # noqa: E501


class _RawProjectMetaHTMLParser(html.parser.HTMLParser):
    api_version: str = "1.0"
    data: str

    def __init__(self) -> None:
        super().__init__()
        self.data = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self.data = ""
        tag_method = f"handle_{tag}_starttag"
        if hasattr(self, tag_method):
            getattr(self, tag_method)(attrs)

    def handle_meta_starttag(self, attrs: list[tuple[str, str | None]]) -> None:
        name = None
        content = None
        for attr, value in attrs:
            match attr:
                case "name":
                    name = value
                case "content":
                    content = value
        if name and name.startswith("pypi:"):
            if content is None:
                raise InvalidHTMLAttributeValue("meta", "content", content)
            pypi_name = name.removeprefix("pypi:")
            method_name = f"handle_{pypi_name.replace('-', '_')}_content"
            try:
                method = getattr(self, method_name)
            except AttributeError:
                pass
            else:
                method(content)

    def handle_repository_version_content(self, content: str) -> None:
        self.api_version = content

    def handle_data(self, data: str) -> None:
        self.data += data

    def handle_endtag(self, tag: str) -> None:
        tag_method = f"handle_{tag}_endtag"
        if hasattr(self, tag_method):
            getattr(self, tag_method)()
        super().handle_endtag(tag)


class _RawProjectListHTMLParser(_RawProjectMetaHTMLParser):
    names: list[str]

    def __init__(self) -> None:
        super().__init__()
        self.names = []

    def handle_a_endtag(self) -> None:
        if data := self.data.strip():
            self.names.append(data)
            self.data = ""


def _normalize_content_type(content_type: str) -> str:
    """Normalize the content type for comparing.

    Critically, this lowercases the content type and remove parameters.

    If a content type is malformed, it defaults to ``text/plain``.
    """
    message = email.message.EmailMessage()
    message["Content-Type"] = content_type
    return message.get_content_type()


def is_supported_content_type(content_type: str) -> bool:
    """Check if the content type is valid for an index server response."""
    cleaned = _normalize_content_type(content_type)
    return cleaned == ACCEPT_JSON_V1 or cleaned in ACCEPT_HTML_VALUES


def parse_list(content_type: str, data: str) -> RawProjectList:
    """Parse the project list based on the specified content type.

    If the content type is :data:`ACCEPT_JSON_V1` then the data string is
    deserialized as JSON. If the content type is from :data:`ACCEPT_HTML` then
    the HTML is parsed and the data is converted to the appropriate JSON
    representation. All other content types raise :exc:`InvalidContentType`.

    Regardless of content type, all data is normalized by storing the canonical
    project names. No other normalization or validation is performed.
    """
    cleaned_content_type = _normalize_content_type(content_type)
    project_list: RawProjectList
    if cleaned_content_type == ACCEPT_JSON_V1:
        project_list = json.loads(data)
    elif cleaned_content_type not in ACCEPT_HTML_VALUES:
        raise InvalidContentType(content_type)
    else:
        with contextlib.closing(_RawProjectListHTMLParser()) as parser:
            parser.feed(data)
        meta = typing.cast("_RawProjectMeta", {"api-version": parser.api_version})
        project_list = {
            "meta": meta,
            "projects": [{"name": name} for name in parser.names],
        }

    for project in project_list["projects"]:
        project["name"] = utils.canonicalize_name(project["name"])

    return project_list


class _RawProjectDetailsHTMLParser(_RawProjectMetaHTMLParser):
    files: list[RawProjectDetailsFile]
    current_file: RawProjectDetailsFile
    status: str | None = None
    status_reason: str | None = None
    base_url: str | None = None

    def __init__(self) -> None:
        super().__init__()
        self.files = []
        self.current_file = self._new_file()

    def _new_file(self) -> RawProjectDetailsFile:
        return {"filename": "", "url": "", "hashes": {}}

    def handle_project_status_content(self, content: str) -> None:
        content_lower = content.lower()
        if content_lower not in {"active", "archived", "quarantined", "deprecated"}:
            raise InvalidHTMLAttributeValue("meta", "content", content)
        self.status = content_lower

    def handle_project_status_reason_content(self, content: str) -> None:
        self.status_reason = content

    def handle_a_starttag(self, attrs: list[tuple[str, str | None]]) -> None:
        self.current_file = self._new_file()
        for name, value in attrs:
            method_name = f"handle_{name.replace('-', '_')}_attr"
            if hasattr(self, method_name):  # pragma: no cover
                getattr(self, method_name)(value)

    def handle_href_attr(self, value: str | None) -> None:
        if value:
            hashes = {}
            self.current_file["url"] = value
            _, fragment = urllib.parse.urldefrag(value)
            for item in fragment.split("&"):
                key, _, val = item.partition("=")
                if not (key and val) or "=" in val:
                    continue
                hash_algo = key.lower()
                if hash_algo not in hashlib.algorithms_available:
                    continue
                hashes[hash_algo] = val
            self.current_file["hashes"] = hashes

    def _process_metadata(
        self, key: Literal["core-metadata", "dist-info-metadata"], value: str | None
    ) -> None:
        result: dict[str, str] | bool = True
        if value:
            if "=" in value:
                hash_algo, _, hash_value = value.partition("=")
                if not hash_algo or not hash_value:
                    raise InvalidHTMLAttributeValue("a", f"data-{key}", value)
                result = {hash_algo: hash_value}
            elif value != "true":
                raise InvalidHTMLAttributeValue("a", f"data-{key}", value)
        self.current_file[key] = result

    def handle_data_core_metadata_attr(self, value: str | None) -> None:
        self._process_metadata("core-metadata", value)

    def handle_data_dist_info_metadata_attr(self, value: str | None) -> None:
        self._process_metadata("dist-info-metadata", value)

    def handle_data_gpg_sig_attr(self, value: str | None) -> None:
        match value:
            case "true":
                has_sig = True
            case "false":
                has_sig = False
            case _:
                raise InvalidHTMLAttributeValue("a", "data-gpg-sig", value)
        self.current_file["gpg-sig"] = has_sig

    def handle_data_requires_python_attr(self, value: str | None) -> None:
        self.current_file["requires-python"] = value or ""

    def handle_data_yanked_attr(self, value: str | None) -> None:
        self.current_file["yanked"] = value or True

    def handle_data_provenance_attr(self, value: str | None) -> None:
        if value is None:
            raise InvalidHTMLAttributeValue("a", "data-provenance", value)
        self.current_file["provenance"] = value

    def handle_base_starttag(self, attrs: list[tuple[str, str | None]]) -> None:
        for attr, value in attrs:
            if attr == "href":
                self.base_url = value
                break

    def handle_a_endtag(self) -> None:
        if "url" in self.current_file:  # No href, no file.
            self.current_file["filename"] = self.data.strip()
            self.files.append(self.current_file)
        self.data = ""
        self.current_file = self._new_file()


@typing.overload
def parse_details(
    content_type: str,
    data: str,
    *,
    name: str,
    request_url: str | None = None,
) -> RawProjectDetails: ...


@typing.overload
def parse_details(
    content_type: str,
    data: str,
    *,
    name: str | None = None,
    request_url: str,
) -> RawProjectDetails: ...


def parse_details(
    content_type: str,
    data: str,
    *,
    name: str | None = None,
    request_url: str | None = None,
) -> RawProjectDetails:
    """Parse the project details response from an index server based on *content_type*.

    Either *name* or *request_url* must be provided in order to have the
    project name for an HTML response. If *request_url* is provided then the
    last portion of the URL is used for the project name.

    If the content type is :data:`ACCEPT_JSON_V1` then the data string is
    deserialized as JSON. If the content type is from :data:`ACCEPT_HTML` then
    the HTML is parsed and the data is converted to the appropriate JSON
    representation. All other content types raise :exc:`InvalidContentType`.

    When invalid data is detected while parsing HTML,
    :exc:`InvalidHTMLAttributeValue` is raised. Attempts are made, though, to
    accept non-standard but unambiguous results (.e.g, the data-core-metadata
    attribute being specified with no value).

    Some normalization is done regardless of the content type. The 'name' key
    is made canonical. If *request_url* -- which is expected to be the URL used
    to make the request -- is provided then the 'url' key is used to make
    sure the URL provided is absolute. If either the 'core-metadata' or
    'dist-info-metadata' key is set and the other is not then the unset key is
    filled with the other's value. Any dictionaries containing hash algorithm
    names as keys will have those name lowercased.
    """
    if not name and not request_url:
        raise TypeError("expected either 'name' or request_url to be provided")
    base_url = request_url
    cleaned_content_type = _normalize_content_type(content_type)
    project_details: RawProjectDetails
    if cleaned_content_type == ACCEPT_JSON_V1:
        project_details = json.loads(data)
    elif cleaned_content_type not in ACCEPT_HTML_VALUES:
        raise InvalidContentType(content_type)
    else:
        with contextlib.closing(_RawProjectDetailsHTMLParser()) as parser:
            parser.feed(data)
        meta = typing.cast("_RawProjectMeta", {"api-version": parser.api_version})

        if name:
            project_name = name
        else:
            # request_url is guaranteed to be a string if 'name' is not set.
            path = typing.cast("str", urllib.parse.urlsplit(request_url).path)
            project_name = path.removesuffix("/").rpartition("/")[-1]

        if parser.base_url:
            base_url = parser.base_url

        project_details = {
            "meta": meta,
            "name": utils.canonicalize_name(project_name),
            "files": parser.files,
        }

        if parser.status:
            project_details.setdefault("project-status", {})["status"] = typing.cast(
                "_PROJECT_STATUSES", parser.status
            )

        if parser.status_reason is not None:
            project_details.setdefault("project-status", {})["reason"] = (
                parser.status_reason
            )

    project_details["name"] = utils.canonicalize_name(project_details["name"])
    for file in project_details["files"]:
        for keys_with_hash_dicts in ["core-metadata", "dist-info-metadata", "hashes"]:
            hashes = file.get(keys_with_hash_dicts, {})
            if not isinstance(hashes, dict):
                continue
            for key in list(hashes.keys()):
                value = hashes.pop(key)
                hashes[key.lower()] = value

        if "core-metadata" in file and "dist-info-metadata" not in file:
            file["dist-info-metadata"] = file["core-metadata"]
        elif "dist-info-metadata" in file and "core-metadata" not in file:
            file["core-metadata"] = file["dist-info-metadata"]

        # XXX check file["url"] exists
        if base_url and not file["url"].startswith(("http://", "https://", "file://")):
            file["url"] = urllib.parse.urljoin(base_url, file["url"])

    return project_details
