from __future__ import annotations

# Make sure anyone importing this module just for the 'Accept' header values
# doesn't pay an unnecessary import penalty for other code.
__lazy_modules__ = {
    "contextlib",
    "email.message",
    "html",
    "json",
    "urllib.parse",
    f"{__spec__.parent}.utils",
}
import contextlib
import email.message
import html
import html.parser  # HTMLParser used as a base class.
import json
import typing  # The `from ... import` forces an eager import.
import urllib.parse
from typing import Literal, TypedDict  # TypedDict is used as a base class.

from . import utils


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
_ACCEPT_HTML_VALUES = ["application/vnd.pypi.simple.v1+html", "text/html"]
ACCEPT_HTML = f"{_ACCEPT_HTML_VALUES[0]}, {_ACCEPT_HTML_VALUES[1]};q=0.01"
"""The HTTP ``Accept`` header value for the HTML API."""
ACCEPT = ", ".join(
    [
        ACCEPT_JSON_V1,
        f"{_ACCEPT_HTML_VALUES[0]};q=0.02",
        f"{_ACCEPT_HTML_VALUES[1]};q=0.01",
    ]
)
"""The HTTP ``Accept`` header value for all supported response types with JSON prioritized."""  # noqa: E501


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
    parsing_anchor: bool

    def __init__(self) -> None:
        super().__init__()
        self.names = []

    def handle_a_endtag(self) -> None:
        self.names.append(self.data.strip())
        self.data = ""


def _normalize_content_type(content_type: str) -> str:
    """Normalize the content type for comparing.

    Critically, this lowercases the content type and remove parameters.

    If a content type is malformed, it defaults to ``text/plain``.
    """
    message = email.message.EmailMessage()
    message["Content-Type"] = content_type
    return message.get_content_type()


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
    elif cleaned_content_type not in _ACCEPT_HTML_VALUES:
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
    current_file: dict[str, typing.Any]
    status: str | None = None
    status_reason: str | None = None
    base_url: str | None = None

    def __init__(self) -> None:
        super().__init__()
        self.files = []
        self.current_file = self._new_file()

    def _new_file(self) -> dict[str, typing.Any]:
        return {"hashes": {}}

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
        if value:  # pragma: no cover
            self.current_file["url"] = value
            if fragment := urllib.parse.urlsplit(value).fragment:
                if fragment.count("=") != 1:
                    raise InvalidHTMLAttributeValue("a", "href", value)
                hash_algo, _, hash_value = fragment.partition("=")
                if not hash_algo or not hash_value:
                    raise InvalidHTMLAttributeValue("a", "href", value)
                self.current_file["hashes"][hash_algo] = hash_value

    def _process_metadata(self, key: str, value: str | None) -> None:
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
        if value is None:
            raise InvalidHTMLAttributeValue("a", "data-requires-python", value)
        self.current_file["requires-python"] = html.unescape(value)

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
        self.current_file["filename"] = self.data.strip()
        self.files.append(typing.cast("RawProjectDetailsFile", self.current_file))
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
    to make the request -- is provided then the 'filename' key is used to make
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
    elif cleaned_content_type not in _ACCEPT_HTML_VALUES:
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
        if (
            base_url
            and "url" in file
            and not file["url"].startswith(("http://", "https://", "file://"))
        ):
            file["url"] = urllib.parse.urljoin(base_url, file["url"])

    return project_details
