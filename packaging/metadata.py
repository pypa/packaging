from __future__ import annotations

import enum
import typing

from . import specifiers
from . import utils

if typing.TYPE_CHECKING:
    from collections.abc import Iterable
    from typing import List, Optional, Set, Tuple

    from . import requirements
    from . import version as packaging_version  # Alt name avoids shadowing.


class InvalidMetadata(ValueError):
    """
    Invalid metadata found.
    """


@enum.unique
class MetadataVersion(enum.Enum):

    """
    Core metadata versions.
    """

    V1_0 = "1.0"
    V1_1 = "1.1"
    V1_2 = "1.2"
    V2_1 = "2.1"
    V2_2 = "2.2"


@enum.unique
class DynamicField(enum.Enum):

    """
    Field names for the `dynamic` field.

    All values are lower-cased for easy comparison.
    """

    # `Name`, `Version`, and `Metadata-Version` are invalid in `Dynamic`.
    # 1.0
    PLATFORM = "platform"
    SUMMARY = "summary"
    DESCRIPTION = "description"
    KEYWORDS = "keywords"
    HOME_PAGE = "home-page"
    AUTHOR = "author"
    AUTHOR_EMAIL = "author-email"
    LICENSE = "license"
    # 1.1
    SUPPORTED_PLATFORM = "supported-platform"
    DOWNLOAD_URL = "download-url"
    CLASSIFIER = "classifier"
    # 1.2
    MAINTAINER = "maintainer"
    MAINTAINER_EMAIL = "maintainer-email"
    REQUIRES_DIST = "requires-dist"
    REQUIRES_PYTHON = "requires-python"
    REQUIRES_EXTERNAL = "requires-external"
    PROJECT_URL = "project-url"
    PROVIDES_DIST = "provides-dist"
    OBSOLETES_DIST = "obsoletes-dist"
    # 2.1
    DESCRIPTION_CONTENT_TYPE = "description-content-type"
    PROVIDES_EXTRA = "provides-extra"


# Type aliases.
_NameAndEmail = Tuple[Optional[str], str]
_LabelAndURL = Tuple[str, str]


class Metadata:

    """
    A representation of core metadata.
    """

    # A property named `display_name` exposes the value.
    _display_name: str
    # A property named `canonical_name` exposes the value.
    _canonical_name: utils.NormalizedName
    version: packaging_version.Version
    platforms: Set[str]
    summary: str
    description: str
    keywords: List[str]
    home_page: str
    author: str
    author_emails: List[_NameAndEmail]
    license: str
    supported_platforms: Set[str]
    download_url: str
    classifiers: Set[str]
    maintainer: str
    maintainer_emails: List[_NameAndEmail]
    requires_dists: Set[requirements.Requirement]
    requires_python: specifiers.SpecifierSet
    requires_externals: Set[str]
    project_urls: Set[_LabelAndURL]
    provides_dists: Set[requirements.Requirement]
    obsoletes_dists: Set[requirements.Requirement]
    description_content_type: str
    provides_extras: Set[str]
    dynamic: Set[DynamicField]

    def __init__(
        self,
        name: str,
        version: packaging_version.Version,
        *,
        # 1.0
        platforms: Optional[Iterable[str]] = None,
        summary: Optional[str] = None,
        description: Optional[str] = None,
        keywords: Optional[Iterable[str]] = None,
        home_page: Optional[str] = None,
        author: Optional[str] = None,
        author_emails: Optional[Iterable[_NameAndEmail]] = None,
        license: Optional[str] = None,
        # 1.1
        supported_platforms: Optional[Iterable[str]] = None,
        download_url: Optional[str] = None,
        classifiers: Optional[Iterable[str]] = None,  # TODO: OK?
        # 1.2
        maintainer: Optional[str] = None,
        maintainer_emails: Optional[Iterable[_NameAndEmail]] = None,
        requires_dists: Optional[Iterable[requirements.Requirement]] = None,
        requires_python: Optional[specifiers.SpecifierSet] = None,
        requires_externals: Optional[Iterable[str]] = None,  # TODO: OK?
        project_urls: Optional[Iterable[_LabelAndURL]] = None,
        provides_dists: Optional[Iterable[requirements.Requirement]] = None,
        obsoletes_dists: Optional[Iterable[requirements.Requirement]] = None,
        # 2.1
        description_content_type: Optional[str] = None,  # TODO: OK?
        provides_extras: Optional[Iterable[str]] = None,  # TODO: OK?
        # 2.2
        dynamic: Optional[Iterable[DynamicField]] = None,
    ) -> None:
        """
        Set all attributes on the instance.

        An argument of `None` will be converted to an appropriate, false-y value
        (e.g. the empty string).
        """
        self.display_name = name
        self.version = version
        self.platforms = set(platforms or [])
        self.summary = summary or ""
        self.description = description or ""
        self.keywords = list(keywords or [])
        self.home_page = home_page or ""
        self.author = author or ""
        self.author_emails = list(author_emails or [])
        self.license = license or ""
        self.supported_platforms = set(supported_platforms or [])
        self.download_url = download_url or ""
        self.classifiers = set(classifiers or [])
        self.maintainer = maintainer or ""
        self.maintainer_emails = list(maintainer_emails or [])
        self.requires_dists = set(requires_dists or [])
        self.requires_python = requires_python or specifiers.SpecifierSet()
        self.requires_externals = set(requires_externals or [])
        self.project_urls = set(project_urls or [])
        self.provides_dists = set(provides_dists or [])
        self.obsoletes_dists = set(obsoletes_dists or [])
        self.description_content_type = description_content_type or ""
        self.provides_extras = set(provides_extras or [])
        self.dynamic = set(dynamic or [])

    @property
    def display_name(self) -> str:
        return self._display_name

    @display_name.setter
    def display_name(self, value, /) -> None:
        """"""
        self._display_name = value
        self._canonical_name = utils.canonicalize_name(value)

    # Use functools.cached_property once Python 3.7 support is dropped.
    # Value is set by self.display_name.setter to keep in sync with self.display_name.
    @property
    def canonical_name(self) -> utils.NormalizedName:
        return self._canonical_name
