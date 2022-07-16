import enum
from typing import Iterable, List, Optional, Tuple

from ..requirements import Requirement
from ..specifiers import SpecifierSet
from ..utils import NormalizedName, canonicalize_name
from ..version import Version

# Type aliases.
_NameAndEmail = Tuple[Optional[str], str]
_LabelAndURL = Tuple[str, str]


@enum.unique
class DynamicField(enum.Enum):
    """
    An :class:`enum.Enum` representing fields which can be listed in the ``Dynamic``
    field of `core metadata`_.

    Every valid field is a name on this enum, upper-cased with any ``-`` replaced with
    ``_``. Each value is the field name lower-cased (``-`` are kept). For example, the
    ``Home-page`` field has a name of ``HOME_PAGE`` and a value of ``home-page``.
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
    """A class representing the `Core Metadata`_ for a project.

    Every potential metadata field except for ``Metadata-Version`` is represented by a
    parameter to the class' constructor. The required metadata can be passed in
    positionally or via keyword, while all optional metadata can only be passed in via
    keyword.

    Every parameter has a matching attribute on instances, except for *name* (see
    :attr:`display_name` and :attr:`canonical_name`). Any parameter that accepts an
    :class:`~collections.abc.Iterable` is represented as a :class:`list` on the
    corresponding attribute.
    """

    # A property named `display_name` exposes the value.
    _display_name: str
    # A property named `canonical_name` exposes the value.
    _canonical_name: NormalizedName
    version: Version
    platforms: List[str]
    summary: str
    description: str
    keywords: List[str]
    home_page: str
    author: str
    author_emails: List[_NameAndEmail]
    license: str
    supported_platforms: List[str]
    download_url: str
    classifiers: List[str]
    maintainer: str
    maintainer_emails: List[_NameAndEmail]
    requires_dists: List[Requirement]
    requires_python: SpecifierSet
    requires_externals: List[str]
    project_urls: List[_LabelAndURL]
    provides_dists: List[str]
    obsoletes_dists: List[str]
    description_content_type: str
    provides_extras: List[NormalizedName]
    dynamic_fields: List[DynamicField]

    def __init__(
        self,
        name: str,
        version: Version,
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
        classifiers: Optional[Iterable[str]] = None,
        # 1.2
        maintainer: Optional[str] = None,
        maintainer_emails: Optional[Iterable[_NameAndEmail]] = None,
        requires_dists: Optional[Iterable[Requirement]] = None,
        requires_python: Optional[SpecifierSet] = None,
        requires_externals: Optional[Iterable[str]] = None,
        project_urls: Optional[Iterable[_LabelAndURL]] = None,
        provides_dists: Optional[Iterable[str]] = None,
        obsoletes_dists: Optional[Iterable[str]] = None,
        # 2.1
        description_content_type: Optional[str] = None,
        provides_extras: Optional[Iterable[NormalizedName]] = None,
        # 2.2
        dynamic_fields: Optional[Iterable[DynamicField]] = None,
    ) -> None:
        """Initialize a Metadata object.

        The parameters all correspond to fields in `Core Metadata`_.

        :param name: ``Name``
        :param version: ``Version``
        :param platforms: ``Platform``
        :param summary: ``Summary``
        :param description: ``Description``
        :param keywords: ``Keywords``
        :param home_page: ``Home-Page``
        :param author: ``Author``
        :param author_emails:
            ``Author-Email`` (two-item tuple represents the name and email of the
            author)
        :param license: ``License``
        :param supported_platforms: ``Supported-Platform``
        :param download_url: ``Download-URL``
        :param classifiers: ``Classifier``
        :param maintainer: ``Maintainer``
        :param maintainer_emails:
            ``Maintainer-Email`` (two-item tuple represent the name and email of the
            maintainer)
        :param requires_dists: ``Requires-Dist``
        :param SpecifierSet requires_python: ``Requires-Python``
        :param requires_externals: ``Requires-External``
        :param project_urls: ``Project-URL``
        :param provides_dists: ``Provides-Dist``
        :param obsoletes_dists: ``Obsoletes-Dist``
        :param description_content_type: ``Description-Content-Type``
        :param provides_extras: ``Provides-Extra``
        :param dynamic_fields: ``Dynamic``
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
        self.requires_python = requires_python or SpecifierSet()
        self.requires_externals = list(requires_externals or [])
        self.project_urls = list(project_urls or [])
        self.provides_dists = list(provides_dists or [])
        self.obsoletes_dists = list(obsoletes_dists or [])
        self.description_content_type = description_content_type or ""
        self.provides_extras = list(provides_extras or [])
        self.dynamic_fields = list(dynamic_fields or [])

    @property
    def display_name(self) -> str:
        """
        The project name to be displayed to users (i.e. not normalized). Initially
        set based on the `name` parameter.

        Setting this attribute will also update :attr:`canonical_name`.
        """
        return self._display_name

    @display_name.setter
    def display_name(self, value: str) -> None:
        self._display_name = value
        self._canonical_name = canonicalize_name(value)

    # Use functools.cached_property once Python 3.7 support is dropped.
    # Value is set by self.display_name.setter to keep in sync with self.display_name.
    @property
    def canonical_name(self) -> NormalizedName:
        """
        The normalized project name as per :func:`packaging.utils.canonicalize_name`.

        The attribute is read-only and automatically calculated based on the value of
        :attr:`display_name`.
        """
        return self._canonical_name
