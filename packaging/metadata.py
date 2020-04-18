# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.
from __future__ import absolute_import, division, print_function

from email.parser import Parser as _EmailParser
from email.message import Message as _EmailMessage
from json import dumps as _json_dumps
from re import compile as _re_compile, IGNORECASE as _IGNORECASE
from warnings import warn

from .requirements import Requirements as _Requirements
from .version import parse as _version_parse

MAX_PROJECT_URL_LABEL_SIZE = 30
SUPPORTED_METADATA_VERSIONS = {"1.0", "1.1", "1.2", "2.1"}
RARELY_DEFINED_TEXT = "{} is a rarely-used field, check whether its use is appropriate"
NO_SEMANTICS_TEXT = (
    "{} has no defined semantics about how the field should be treated. "
    "You may want to check other fields, or the list of classifiers to see "
    "if there is a more appropriate field or classifier, or look at some "
    "other mechanism to achieve your aim."
)
_PACKAGE_NAME_REGEX = _re_compile(
    "^([A-Z0-9]|[A-Z0-9][A-Z0-9._-]*[A-Z0-9])$", _IGNORECASE
)


def _to_python_name(name):
    return name.lower().replace("-", "_")


class RarelyUsedMetadata(Warning):
    pass


class DeprecatedMetadata(Warning):
    pass


class MetadataLacksSemantics(Warning):
    pass


class MissingRequiredMetadata(ValueError):
    pass


class InvalidMetadata(ValueError):
    pass


class UnknownMetadataVersion(ValueError):
    pass


def _validate_metadata_version(version):
    if version == "2.0":
        warn(
            "Version 2.0 was never standardised, you will want to move to "
            "version 2.1, which can be done by setting metadata_version to "
            "'2.1'."
        )
    elif version not in SUPPORTED_METADATA_VERSIONS:
        if version.startswith("1."):
            warn("There is no metadata version {}, converting to 2.1".format(version))
            return "2.1"
        if version.startswith("2."):
            warn("{} is not supported yet, there may be missing fields".format(version))
            return version
        raise UnknownMetadataVersion(
            "Unsupported major metadata version {}".format(version)
        )

    return version


def _validate_package_name(name):
    if _PACKAGE_NAME_REGEX.match(name):
        return name
    raise InvalidMetadata("{} is not a valid package name".format(name))


def _validate_summary(summary):
    if "\n" in summary or "\r" in summary:
        raise InvalidMetadata("summary should only have one line")
    return summary


def _validate_content_type(content_type):
    return content_type


def _validate_keywords(keywords):
    if "," in keywords:
        return keywords.split(",")
    return keywords.split()


def _validate_project_url(urls):
    d = {}
    for labelled_url in urls:
        label, url = labelled_url.split(",")
        label = label.strip()
        if len(label) > MAX_PROJECT_URL_LABEL_SIZE:
            raise InvalidMetadata(
                "project_url label must be less than {} signs".format(
                    MAX_PROJECT_URL_LABEL_SIZE
                )
            )
        d[label] = url.strip()
    return d


def _validate_requirements(requirements):
    return _Requirements(requirements)


class MetadataField(object):
    def __init__(
        self,
        name,
        required=False,
        deprecated=False,
        rarely_used=False,
        multiple_use=False,
        validator=None,
        as_dict=None,
        as_json=None,
        deprecated_by=None,
        no_semantics=False,
        as_str=None,
    ):
        self.name = name
        self.python_name = _to_python_name(self.name)
        self.required = required
        self.deprecated = deprecated
        self.deprecated_by = deprecated_by
        self.rarely_used = rarely_used
        self.multiple_use = multiple_use
        self.no_semantics = no_semantics

        self.validator = validator
        self.as_str = as_str if as_str is not None else self._to_str
        self.as_dict = as_dict if as_dict is not None else self._to_dict
        self.as_json = as_json if as_json is not None else self.as_dict

    def _to_str(self, obj, msg):
        if hasattr(obj, self.python_name):
            if self.multiple_use:
                for val in getattr(obj, self.python_name):
                    msg[self.name] = val
            else:
                msg[self.name] = str(getattr(obj, self.python_name))
        elif self.required:
            raise MissingRequiredMetadata(
                "Cannot write metadata, missing {}".format(self.python_name)
            )

    def _to_dict(self, obj):
        if hasattr(obj, self.python_name):
            return {self.python_name: getattr(obj, self.python_name)}
        return {}

    def __get__(self, obj, objtype):
        return getattr(obj, "_" + self.python_name)

    def __set__(self, obj, val):
        if self.deprecated:
            if self.deprecated_by is not None:
                warn(
                    "{} is a deprecated field, replaced by {}".format(
                        self.python_name, self.deprecated_by
                    ),
                    DeprecatedMetadata,
                )
            else:
                warn(
                    "{} is a deprecated field".format(self.python_name),
                    DeprecatedMetadata,
                )

        if self.rarely_used:
            warn(RARELY_DEFINED_TEXT.format(self.python_name), RarelyUsedMetadata)

        if self.no_semantics:
            warn(NO_SEMANTICS_TEXT.format(self.python_name), MetadataLacksSemantics)

        if self.multiple_use and isinstance(val, str):
            val = [val]

        if self.validator is not None:
            val = self.validator(val)

        setattr(obj, "_" + self.python_name, val)

    def __delete__(self, obj):
        raise AttributeError("can't delete attribute {}".format(self.python_name))


class Metadata(object):
    metadata_version = MetadataField(
        "Metadata-Version", required=True, validator=_validate_metadata_version
    )
    name = MetadataField("Name", required=True, validator=_validate_package_name)
    version = MetadataField("Version", required=True, validator=_version_parse)
    platform = MetadataField("Platform", multiple_use=True)
    supported_platform = MetadataField(
        "Supported-Platform", no_semantics=True, multiple_use=True
    )
    summary = MetadataField("Summary", required=True, validator=_validate_summary)
    description = MetadataField("Description")
    description_content_type = MetadataField(
        "Description-Content-Type", validator=_validate_content_type
    )
    keywords = MetadataField("Keywords", validator=_validate_keywords)
    home_page = MetadataField("Home-page")
    download_url = MetadataField("Download-URL")
    author = MetadataField("Author")
    author_email = MetadataField("Author-email", required=True)
    maintainer = MetadataField("Maintainer")
    maintainer_email = MetadataField("Maintainer-email")
    license = MetadataField("License", required=True)
    classifier = MetadataField("Classifier", multiple_use=True)
    requires_dist = MetadataField(
        "Requires-Dist", multiple_use=True, validator=_validate_requirements
    )
    requires_python = MetadataField("Requires-Python", multiple_use=True)
    requires_external = MetadataField("Requires-External", multiple_use=True)
    project_url = MetadataField(
        "Project-URL", multiple_use=True, validator=_validate_project_url
    )
    provides_extra = MetadataField("Provides-Extra", multiple_use=True)
    provides_dist = MetadataField(
        "Provides-Dist",
        multiple_use=True,
        rarely_used=True,
        validator=_validate_requirements,
    )
    obsoletes_dist = MetadataField(
        "Obsoletes-Dist",
        multiple_use=True,
        rarely_used=True,
        validator=_validate_requirements,
    )
    requires = MetadataField(
        "Requires",
        multiple_use=True,
        deprecated=True,
        deprecated_by=requires_dist,
        validator=_validate_requirements,
    )
    provides = MetadataField(
        "Provides",
        multiple_use=True,
        deprecated=True,
        deprecated_by=provides_dist,
        validator=_validate_requirements,
    )
    obsoletes = MetadataField(
        "Obsoletes",
        multiple_use=True,
        deprecated=True,
        deprecated_by=obsoletes_dist,
        validator=_validate_requirements,
    )

    def __init__(self, **kwargs):
        self._metadata_fields_ = {}
        required_fields = []
        other_fields = []
        for name, attr in type(self).__dict__.items():
            if isinstance(attr, MetadataField):
                self._metadata_fields_[name] = attr
                if attr.required:
                    required_fields.append(name)
                else:
                    other_fields.append(name)

        required_fields.remove("metadata_version")
        mv = kwargs.pop("metadata_version", None)
        if mv is None:
            raise MissingRequiredMetadata("Missing required metadata metadata_version")
        self.metadata_version = mv
        for name in required_fields:
            val = kwargs.pop(name, None)
            if val is None:
                raise MissingRequiredMetadata(
                    "Missing required metadata {}".format(name)
                )
            setattr(self, name, val)
        for name in other_fields:
            val = kwargs.pop(name, None)
            if val is not None:
                setattr(self, name, val)

        if kwargs:
            warn("Extra metadata {}".format(kwargs))

    @classmethod
    def from_path_(cls, path):
        with open(path, "r") as f:
            return cls.from_file_(f)

    @classmethod
    def from_file_(cls, file):
        parser = _EmailParser()
        return cls._from_msg_(parser.parse(file))

    @classmethod
    def from_str_(cls, string):
        parser = _EmailParser()
        return cls._from_msg_(parser.parsestr(string))

    @classmethod
    def _from_msg_(cls, msg):
        body = msg.get_payload()
        metadata = {}
        for name in msg.keys():
            python_name = _to_python_name(name)
            val = msg.get_all(name)
            if len(val) == 1:
                val = val[0]
            metadata[python_name] = val
        if body:
            metadata["description"] = body
        return cls(**metadata)

    def as_dict_(self):
        d = {}
        for field in self._metadata_fields_.values():
            d.update(**field.as_dict(self))
        return d

    def as_json_(self):
        d = {}
        for field in self._metadata_fields_.values():
            d.update(**field.as_json(self))
        return _json_dumps(d)

    def as_str_(self):
        msg = _EmailMessage()
        for field in self._metadata_fields_.values():
            field.as_str(self, msg)
        return msg.as_string()

    def to_file(self, file):
        file.write(self.as_str_())

    def to_path(self, path):
        with open(path, "w") as f:
            self.to_file(f)
