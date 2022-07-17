from __future__ import annotations

import enum
from typing import Optional, Tuple, TypedDict

from ..version import Version
from ._validation import RegexValidator, Required, eagerly_validate, lazy_validator
from .raw import RawMetadata, parse_email, parse_json

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


class _ValidatedMetadata(TypedDict, total=False):
    # Metadata 1.0 - PEP 241
    name: str
    version: Version
    # platforms: List[str]
    # summary: str
    # description: str
    # keywords: List[str]
    # home_page: str
    # author: str
    # author_email: str
    # license: str


class Metadata:

    # We store our "actual" metadata as a RawMetadata, which
    # gives is a little bit of indirection here. The RawMetadata
    # class is lenient as to what it will consider valid, but this
    # class is not.
    #
    # However, we want to support validation to happen both up front
    # and on the fly as you access attributes, and when using the
    # on the fly validation, we don't want to validate anything else
    # except for the specific piece of metadata that is being
    # asked for.
    #
    # That means that we need to store, at least initially, the
    # metadata in a form that is lenient, which is exactly the
    # purpose of RawMetadata.
    _raw: RawMetadata

    # Likewise, we need a place to store our honest to goodness actually
    # validated metadata too, we could just store this in a dict, but
    # this will give us better typing.
    _validated: _ValidatedMetadata

    def __init__(self) -> None:
        raise NotImplementedError

    # It's not exactly the most pythonic thing to have a bunch of getter/setters
    # like this for every attribute, however this enables us to do our on the
    # fly validation.

    # Name: Metadata 1.0
    name = lazy_validator(
        str,
        validators=[
            Required(),
            RegexValidator("(?i)^([A-Z0-9]|[A-Z0-9][A-Z0-9._-]*[A-Z0-9])$"),
        ],
    )
    # Version: Metadata 1.0
    version = lazy_validator(Version, validators=[Required()])

    @classmethod
    def from_raw(cls, raw: RawMetadata, *, validate: bool = True) -> Metadata:
        # Ok this is some kind of gross code here, but it has a specific
        # purpose.
        #
        # We want to enable the progrmatic API of the Metadata
        # class to strictly validate, including requires data, so
        # we want something like Metadata("foo", "1.0", ...), but
        # we also want from_raw to *not* require that data, so we
        # treat our __init__ as our public constructor, then we bypass
        # the __init__ when calling from_raw to let us setup the object
        # in a completely different way, without exposing that as
        # programatic API in and of itself.
        meta = cls.__new__(cls)
        meta._raw = raw
        meta._validated = _ValidatedMetadata()

        # It's not possible to use Metadata without validating, but the
        # validate parameter here lets people control whether the entire
        # metadata gets validated up front, or whether it gets validated
        # on demand.
        if validate:
            eagerly_validate(meta)

        return meta

    @classmethod
    def from_email(cls, data: bytes | str, *, validate: bool = True) -> Metadata:
        raw, unparsed = parse_email(data)

        # Regardless of the validate attribute, we don't let unparsed data
        # pass silently, if someone wants to drop unparsed data on the floor
        # they can call parse_email themselves and pass it into from_raw
        if unparsed:
            raise ValueError(
                f"Could not parse, extra keys: {', '.join(unparsed.keys())}"
            )

        return cls.from_raw(raw, validate=validate)

    @classmethod
    def from_json(cls, data: bytes | str, *, validate: bool = True) -> Metadata:
        raw, unparsed = parse_json(data)

        # Regardless of the validate attribute, we don't let unparsed data
        # pass silently, if someone wants to drop unparsed data on the floor
        # they can call parse_email themselves and pass it into from_raw
        if unparsed:
            raise ValueError(
                f"Could not parse, extra keys: {', '.join(unparsed.keys())}"
            )

        return cls.from_raw(raw, validate=validate)
