import email.feedparser
import email.header
import email.message
import email.parser
import email.policy
import functools
import sys
import typing
from typing import Any, Callable, Dict, Generic, List, Optional, Tuple, Union, cast

from . import requirements, specifiers, utils, version as version_module

T = typing.TypeVar("T")

if sys.version_info >= (3, 8):  # pragma: no cover
    from typing import Literal, TypedDict
else:  # pragma: no cover
    if typing.TYPE_CHECKING:
        from typing_extensions import Literal, TypedDict
    else:
        try:
            from typing_extensions import Literal, TypedDict
        except ImportError:

            class Literal:
                def __init_subclass__(*_args, **_kwargs):
                    pass

            class TypedDict:
                def __init_subclass__(*_args, **_kwargs):
                    pass


class InvalidMetadata(ValueError):
    """A metadata field contains invalid data."""

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
    field have a key with a plural name.

    Core metadata fields that can be specified multiple times are stored as a
    list or dict depending on which is appropriate for the field. Any fields
    which hold multiple values in a single field are stored as a list.

    """

    # Metadata 1.0 - PEP 241
    metadata_version: str
    name: str
    version: str
    platforms: List[str]
    summary: str
    description: str
    keywords: List[str]
    home_page: str
    author: str
    author_email: str
    license: str

    # Metadata 1.1 - PEP 314
    supported_platforms: List[str]
    download_url: str
    classifiers: List[str]
    requires: List[str]
    provides: List[str]
    obsoletes: List[str]

    # Metadata 1.2 - PEP 345
    maintainer: str
    maintainer_email: str
    requires_dist: List[str]
    provides_dist: List[str]
    obsoletes_dist: List[str]
    requires_python: str
    requires_external: List[str]
    project_urls: Dict[str, str]

    # Metadata 2.0
    # PEP 426 attempted to completely revamp the metadata format
    # but got stuck without ever being able to build consensus on
    # it and ultimately ended up withdrawn.
    #
    # However, a number of tools had started emiting METADATA with
    # `2.0` Metadata-Version, so for historical reasons, this version
    # was skipped.

    # Metadata 2.1 - PEP 566
    description_content_type: str
    provides_extra: List[str]

    # Metadata 2.2 - PEP 643
    dynamic: List[str]

    # Metadata 2.3 - PEP 685
    # No new fields were added in PEP 685, just some edge case were
    # tightened up to provide better interoptability.


_STRING_FIELDS = {
    "author",
    "author_email",
    "description",
    "description_content_type",
    "download_url",
    "home_page",
    "license",
    "maintainer",
    "maintainer_email",
    "metadata_version",
    "name",
    "requires_python",
    "summary",
    "version",
}

_LIST_STRING_FIELDS = {
    "classifiers",
    "dynamic",
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
}


def _parse_keywords(data: str) -> List[str]:
    """Split a string of comma-separate keyboards into a list of keywords."""
    return [k.strip() for k in data.split(",")]


def _parse_project_urls(data: List[str]) -> Dict[str, str]:
    """Parse a list of label/URL string pairings separated by a comma."""
    urls = {}
    for pair in data:
        # Our logic is slightly tricky here as we want to try and do
        # *something* reasonable with malformed data.
        #
        # The main thing that we have to worry about, is data that does
        # not have a ',' at all to split the label from the Value. There
        # isn't a singular right answer here, and we will fail validation
        # later on (if the caller is validating) so it doesn't *really*
        # matter, but since the missing value has to be an empty str
        # and our return value is dict[str, str], if we let the key
        # be the missing value, then they'd have multiple '' values that
        # overwrite each other in a accumulating dict.
        #
        # The other potentional issue is that it's possible to have the
        # same label multiple times in the metadata, with no solid "right"
        # answer with what to do in that case. As such, we'll do the only
        # thing we can, which is treat the field as unparseable and add it
        # to our list of unparsed fields.
        parts = [p.strip() for p in pair.split(",", 1)]
        parts.extend([""] * (max(0, 2 - len(parts))))  # Ensure 2 items

        # TODO: The spec doesn't say anything about if the keys should be
        #       considered case sensitive or not... logically they should
        #       be case-preserving and case-insensitive, but doing that
        #       would open up more cases where we might have duplicate
        #       entries.
        label, url = parts
        if label in urls:
            # The label already exists in our set of urls, so this field
            # is unparseable, and we can just add the whole thing to our
            # unparseable data and stop processing it.
            raise KeyError("duplicate labels in project urls")
        urls[label] = url

    return urls


def _get_payload(msg: email.message.Message, source: Union[bytes, str]) -> str:
    """Get the body of the message."""
    # If our source is a str, then our caller has managed encodings for us,
    # and we don't need to deal with it.
    if isinstance(source, str):
        payload: str = msg.get_payload()
        return payload
    # If our source is a bytes, then we're managing the encoding and we need
    # to deal with it.
    else:
        bpayload: bytes = msg.get_payload(decode=True)
        try:
            return bpayload.decode("utf8", "strict")
        except UnicodeDecodeError:
            raise ValueError("payload in an invalid encoding")


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
    "keywords": "keywords",
    "license": "license",
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


def parse_email(data: Union[bytes, str]) -> Tuple[RawMetadata, Dict[str, List[str]]]:
    """Parse a distribution's metadata.

    This function returns a two-item tuple of dicts. The first dict is of
    recognized fields from the core metadata specification. Fields that can be
    parsed and translated into Python's built-in types are converted
    appropriately. All other fields are left as-is. Fields that are allowed to
    appear multiple times are stored as lists.

    The second dict contains all other fields from the metadata. This includes
    any unrecognized fields. It also includes any fields which are expected to
    be parsed into a built-in type but were not formatted appropriately. Finally,
    any fields that are expected to appear only once but are repeated are
    included in this dict.

    """
    raw: Dict[str, Union[str, List[str], Dict[str, str]]] = {}
    unparsed: Dict[str, List[str]] = {}

    if isinstance(data, str):
        parsed = email.parser.Parser(policy=email.policy.compat32).parsestr(data)
    else:
        parsed = email.parser.BytesParser(policy=email.policy.compat32).parsebytes(data)

    # We have to wrap parsed.keys() in a set, because in the case of multiple
    # values for a key (a list), the key will appear multiple times in the
    # list of keys, but we're avoiding that by using get_all().
    for name in frozenset(parsed.keys()):
        # Header names in RFC are case insensitive, so we'll normalize to all
        # lower case to make comparisons easier.
        name = name.lower()

        # We use get_all() here, even for fields that aren't multiple use,
        # because otherwise someone could have e.g. two Name fields, and we
        # would just silently ignore it rather than doing something about it.
        headers = parsed.get_all(name)

        # The way the email module works when parsing bytes is that it
        # unconditionally decodes the bytes as ascii using the surrogateescape
        # handler. When you pull that data back out (such as with get_all() ),
        # it looks to see if the str has any surrogate escapes, and if it does
        # it wraps it in a Header object instead of returning the string.
        #
        # As such, we'll look for those Header objects, and fix up the encoding.
        value = []
        # Flag if we have run into any issues processing the headers, thus
        # signalling that the data belongs in 'unparsed'.
        valid_encoding = True
        for h in headers:
            # It's unclear if this can return more types than just a Header or
            # a str, so we'll just assert here to make sure.
            assert isinstance(h, (email.header.Header, str))

            # If it's a header object, we need to do our little dance to get
            # the real data out of it. In cases where there is invalid data
            # we're going to end up with mojibake, but there's no obvious, good
            # way around that without reimplementing parts of the Header object
            # ourselves.
            #
            # That should be fine since, if mojibacked happens, this key is
            # going into the unparsed dict anyways.
            if isinstance(h, email.header.Header):
                # The Header object stores it's data as chunks, and each chunk
                # can be independently encoded, so we'll need to check each
                # of them.
                chunks: List[Tuple[bytes, Optional[str]]] = []
                for bin, encoding in email.header.decode_header(h):
                    try:
                        bin.decode("utf8", "strict")
                    except UnicodeDecodeError:
                        # Enable mojibake.
                        encoding = "latin1"
                        valid_encoding = False
                    else:
                        encoding = "utf8"
                    chunks.append((bin, encoding))

                # Turn our chunks back into a Header object, then let that
                # Header object do the right thing to turn them into a
                # string for us.
                value.append(str(email.header.make_header(chunks)))
            # This is already a string, so just add it.
            else:
                value.append(h)

        # We've processed all of our values to get them into a list of str,
        # but we may have mojibake data, in which case this is an unparsed
        # field.
        if not valid_encoding:
            unparsed[name] = value
            continue

        raw_name = _EMAIL_TO_RAW_MAPPING.get(name)
        if raw_name is None:
            # This is a bit of a weird situation, we've encountered a key that
            # we don't know what it means, so we don't know whether it's meant
            # to be a list or not.
            #
            # Since we can't really tell one way or another, we'll just leave it
            # as a list, even though it may be a single item list, because that's
            # what makes the most sense for email headers.
            unparsed[name] = value
            continue

        # If this is one of our string fields, then we'll check to see if our
        # value is a list of a single item. If it is then we'll assume that
        # it was emitted as a single string, and unwrap the str from inside
        # the list.
        #
        # If it's any other kind of data, then we haven't the faintest clue
        # what we should parse it as, and we have to just add it to our list
        # of unparsed stuff.
        if raw_name in _STRING_FIELDS and len(value) == 1:
            raw[raw_name] = value[0]
        # If this is one of our list of string fields, then we can just assign
        # the value, since email *only* has strings, and our get_all() call
        # above ensures that this is a list.
        elif raw_name in _LIST_STRING_FIELDS:
            raw[raw_name] = value
        # Special Case: Keywords
        # The keywords field is implemented in the metadata spec as a str,
        # but it conceptually is a list of strings, and is serialized using
        # ", ".join(keywords), so we'll do some light data massaging to turn
        # this into what it logically is.
        elif raw_name == "keywords" and len(value) == 1:
            raw[raw_name] = _parse_keywords(value[0])
        # Special Case: Project-URL
        # The project urls is implemented in the metadata spec as a list of
        # specially-formatted strings that represent a key and a value, which
        # is fundamentally a mapping, however the email format doesn't support
        # mappings in a sane way, so it was crammed into a list of strings
        # instead.
        #
        # We will do a little light data massaging to turn this into a map as
        # it logically should be.
        elif raw_name == "project_urls":
            try:
                raw[raw_name] = _parse_project_urls(value)
            except KeyError:
                unparsed[name] = value
        # Nothing that we've done has managed to parse this, so it'll just
        # throw it in our unparseable data and move on.
        else:
            unparsed[name] = value

    # We need to support getting the Description from the message payload in
    # addition to getting it from the the headers. This does mean, though, there
    # is the possibility of it being set both ways, in which case we put both
    # in 'unparsed' since we don't know which is right.
    try:
        payload = _get_payload(parsed, data)
    except ValueError:
        unparsed.setdefault("description", []).append(
            parsed.get_payload(decode=isinstance(data, bytes))
        )
    else:
        if payload:
            # Check to see if we've already got a description, if so then both
            # it, and this body move to unparseable.
            if "description" in raw:
                description_header = cast(str, raw.pop("description"))
                unparsed.setdefault("description", []).extend(
                    [description_header, payload]
                )
            elif "description" in unparsed:
                unparsed["description"].append(payload)
            else:
                raw["description"] = payload

    # We need to cast our `raw` to a metadata, because a TypedDict only support
    # literal key names, but we're computing our key names on purpose, but the
    # way this function is implemented, our `TypedDict` can only have valid key
    # names.
    return cast(RawMetadata, raw), unparsed


def _required(field: str, value: Any) -> None:
    """Check that the field has a value."""
    if not value:
        raise InvalidMetadata(field, f"{field!r} is a required field")


def _single_line(field: str, value: str) -> None:
    """Check the field contains no newlines."""
    if "\n" in value:
        raise InvalidMetadata(field, f"{field!r} must be a single line")


def _valid_metadata_version(field: str, value: str) -> None:
    if value not in {"1.0", "1.1", "1.2", "2.0", "2.1", "2.2", "2.3"}:
        raise InvalidMetadata(field, f"{value!r} not a valid metadata version")


def _valid_content_type(field: str, value: str) -> None:
    content_types = {"text/plain", "text/x-rst", "text/markdown"}
    message = email.message.EmailMessage()
    message["content-type"] = value
    content_type, parameters = (
        message.get_content_type(),  # Defaults to `text/plain` if not parseable.
        message["content-type"].params,
    )
    # Check if content-type is valid or defaulted to `text/plain` and thus was
    # not parseable.
    if content_type not in content_types or content_type not in value:
        raise InvalidMetadata(
            field, f"{field} must be one of {content_types}, not {value}"
        )

    charset = parameters.get("charset", "UTF-8")
    if charset != "UTF-8":
        raise InvalidMetadata(
            field, f"{field} can only specify a UTF-8 charset, not {charset}"
        )

    markdown_variants = {"GFM", "CommonMark"}
    variant = parameters.get("variant", "GFM")  # Use an acceptable default.
    if content_type == "text/markdown" and variant not in markdown_variants:
        raise InvalidMetadata(
            field,
            f"valid Markdown variants for {field} are {markdown_variants}, "
            f"not {variant}",
        )


def _valid_dynamic(field: str, value: str) -> None:
    for dynamic_field in map(str.lower, value):
        if dynamic_field in {"name", "version", "metadata-version"}:
            raise InvalidMetadata(field, f"{value!r} is not allowed as a dynamic field")
        elif dynamic_field not in _EMAIL_TO_RAW_MAPPING:
            raise InvalidMetadata(field, f"{value!r} is not a valid dynamic field")


_NOT_FOUND = object()

# "2.0" is technically invalid, but people used it while waiting for "2.1".
_MetadataVersion = Literal["1.0", "1.1", "1.2", "2.0", "2.1", "2.2", "2.3"]


class _Validator(Generic[T]):
    name: str
    raw_name: str
    validators: List[Callable[[str, Any], None]]
    converters: List[Callable[[Any], T]]
    added: _MetadataVersion

    def __init__(
        self,
        *,
        validators: List[Callable[[str, Any], None]] = [],
        converters: List[Callable[[Any], T]] = [],
        added: _MetadataVersion = "1.0",
    ) -> None:
        self.validators = validators
        self.converters = converters
        self.added = added

    def __set_name__(self, _owner: "Metadata", name: str) -> None:
        self.name = name
        self.raw_name = _RAW_TO_EMAIL_MAPPING[name]

    def __get__(self, instance: "Metadata", _owner: type["Metadata"]) -> Optional[T]:
        # With Python 3.8, the caching can be replaced with functools.cached_property().
        cache = instance.__dict__
        value = cache.get(self.name, _NOT_FOUND)
        if value is _NOT_FOUND:
            # XXX Is None always the best "missing" value?
            raw_value = instance._raw.get(self.name)
            for validator in self.validators:
                validator(self.raw_name, raw_value)
            value = raw_value
            for converter in self.converters:
                value = converter(value)
            cache[self.name] = value
            try:
                del instance._raw[self.name]  # type: ignore[misc]
            except KeyError:
                pass
        return cast(Optional[T], value)


class Metadata:
    _raw: RawMetadata

    @classmethod
    def from_raw(cls, data: RawMetadata) -> "Metadata":
        ins = cls()
        ins._raw = data
        return ins

    @classmethod
    def from_email(cls, data: Union[bytes, str]) -> "Metadata":
        """Parse metadata from an email message."""
        raw, unparsed = parse_email(data)
        return cls.from_raw(raw)
        # TODO Check `unparsed` for valid keys?

    # TODO Check that fields are specified in a valid metadata version?

    metadata_version: _Validator[_MetadataVersion] = _Validator(
        # Allow for "2.0" as that basically became "2.1".
        validators=[_valid_metadata_version]
    )
    name: _Validator[utils.NormalizedName] = _Validator(
        validators=[_required],
        converters=[functools.partial(utils.canonicalize_name, validate=True)],
    )
    version: _Validator[version_module.Version] = _Validator(
        validators=[_required], converters=[version_module.parse]
    )
    dynamic: _Validator[List[str]] = _Validator(
        validators=[_valid_dynamic],
        converters=[lambda fields: list(map(str.lower, fields))],
        added="2.2",
    )
    platforms: _Validator[str] = _Validator()
    supported_platforms: _Validator[List[str]] = _Validator(added="1.1")
    summary: _Validator[str] = _Validator(validators=[_single_line])
    description: _Validator[str] = _Validator()  # XXX 2.1: can be in body
    # TODO are the various parts of description_content_type case-insensitive?
    description_content_type: _Validator[str] = _Validator(
        validators=[_valid_content_type], added="2.1"
    )
    keywords: _Validator[List[str]] = _Validator()
    home_page: _Validator[str] = _Validator()
    download_url: _Validator[str] = _Validator(added="1.1")
    author: _Validator[str] = _Validator()
    author_email: _Validator[str] = _Validator()
    maintainer: _Validator[str] = _Validator(added="1.2")
    maintainer_email: _Validator[str] = _Validator(added="1.2")
    license: _Validator[str] = _Validator()
    classifiers: _Validator[List[str]] = _Validator(added="1.1")
    requires_dist: _Validator[List[requirements.Requirement]] = _Validator(
        converters=[lambda reqs: list(map(requirements.Requirement, reqs))], added="1.2"
    )
    requires_python: _Validator[specifiers.SpecifierSet] = _Validator(
        converters=[specifiers.SpecifierSet], added="1.2"
    )
    # Because `Requires-External` allows for non-PEP 440 version specifiers, we
    # don't do any processing on the values.
    requires_external: _Validator[List[str]] = _Validator(added="1.2")
    project_urls: _Validator[Dict[str, str]] = _Validator(added="1.2")
    # PEP 685 lets us raise an error if an extra doesn't pass `Name` validation
    # regardless of metadata version.
    provides_extra: _Validator[List[utils.NormalizedName]] = _Validator(
        validators=[
            # XXX Remove the `type: ignore`
            lambda field, names: [  # type: ignore[list-item]
                utils.canonicalize_name(name, validate=True) for name in names
            ]
        ],
        added="2.1",
    )
    provides_dist: _Validator[List[str]] = _Validator(added="1.2")
    obsoletes_dist: _Validator[List[str]] = _Validator(added="1.2")
