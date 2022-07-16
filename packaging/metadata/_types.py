from __future__ import annotations

import enum
from collections.abc import Iterable
from typing import Optional, Tuple

from .. import (  # Alt name avoids shadowing.
    requirements,
    specifiers,
    utils,
    version as packaging_version,
)

# Type aliases.
_NameAndEmail = Tuple[Optional[str], str]
_LabelAndURL = Tuple[str, str]


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


class Metadata:

    """
    A representation of core metadata.
    """

    # A property named `display_name` exposes the value.
    _display_name: str
    # A property named `canonical_name` exposes the value.
    _canonical_name: utils.NormalizedName
    version: packaging_version.Version
    platforms: list[str]
    summary: str
    description: str
    keywords: list[str]
    home_page: str
    author: str
    author_emails: list[_NameAndEmail]
    license: str
    supported_platforms: list[str]
    download_url: str
    classifiers: list[str]
    maintainer: str
    maintainer_emails: list[_NameAndEmail]
    requires_dists: list[requirements.Requirement]
    requires_python: specifiers.SpecifierSet
    requires_externals: list[str]
    project_urls: list[_LabelAndURL]
    provides_dists: list[str]
    obsoletes_dists: list[str]
    description_content_type: str
    provides_extras: list[utils.NormalizedName]
    dynamic_fields: list[DynamicField]

    def __init__(
        self,
        name: str,
        version: packaging_version.Version,
        *,
        # 1.0
        platforms: Iterable[str] | None = None,
        summary: str | None = None,
        description: str | None = None,
        keywords: Iterable[str] | None = None,
        home_page: str | None = None,
        author: str | None = None,
        author_emails: Iterable[_NameAndEmail] | None = None,
        license: str | None = None,
        # 1.1
        supported_platforms: Iterable[str] | None = None,
        download_url: str | None = None,
        classifiers: Iterable[str] | None = None,
        # 1.2
        maintainer: str | None = None,
        maintainer_emails: Iterable[_NameAndEmail] | None = None,
        requires_dists: Iterable[requirements.Requirement] | None = None,
        requires_python: specifiers.SpecifierSet | None = None,
        requires_externals: Iterable[str] | None = None,
        project_urls: Iterable[_LabelAndURL] | None = None,
        provides_dists: Iterable[str] | None = None,
        obsoletes_dists: Iterable[str] | None = None,
        # 2.1
        description_content_type: str | None = None,
        provides_extras: Iterable[utils.NormalizedName] | None = None,
        # 2.2
        dynamic_fields: Iterable[DynamicField] | None = None,
    ) -> None:
        """
        Set all attributes on the instance.

        An argument of `None` will be converted to an appropriate, false-y value
        (e.g. the empty string).
        """
        self.display_name = name
        self.version = version
        self.platforms = list(platforms or [])
        self.summary = summary or ""
        self.description = description or ""
        self.keywords = list(keywords or [])
        self.home_page = home_page or ""
        self.author = author or ""
        self.author_emails = list(author_emails or [])
        self.license = license or ""
        self.supported_platforms = list(supported_platforms or [])
        self.download_url = download_url or ""
        self.classifiers = list(classifiers or [])
        self.maintainer = maintainer or ""
        self.maintainer_emails = list(maintainer_emails or [])
        self.requires_dists = list(requires_dists or [])
        self.requires_python = requires_python or specifiers.SpecifierSet()
        self.requires_externals = list(requires_externals or [])
        self.project_urls = list(project_urls or [])
        self.provides_dists = list(provides_dists or [])
        self.obsoletes_dists = list(obsoletes_dists or [])
        self.description_content_type = description_content_type or ""
        self.provides_extras = list(provides_extras or [])
        self.dynamic_fields = list(dynamic_fields or [])

    @property
    def display_name(self) -> str:
        return self._display_name

    @display_name.setter
    def display_name(self, value: str) -> None:
        """
        Set the value for self.display_name and self.canonical_name.
        """
        self._display_name = value
        self._canonical_name = utils.canonicalize_name(value)

    # Use functools.cached_property once Python 3.7 support is dropped.
    # Value is set by self.display_name.setter to keep in sync with self.display_name.
    @property
    def canonical_name(self) -> utils.NormalizedName:
        return self._canonical_name
