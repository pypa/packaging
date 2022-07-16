import email.feedparser
import email.header
import email.message
import email.parser
import email.policy
import json
from typing import Any, TypedDict, Union, cast


# The RawMetadata class attempts to make as few assumptions about
# the underlying serialization formats as possible, these could
# possibly serialize in an entirely different way, but the idea
# here is that as long as a serialization formats some very
# basic primitives in *some* way (strings, lists, and one map
# but that map can be easily implemented as a list of strings)
# then we can support serializing to and from that format.
class RawMetadata(TypedDict, total=False):
    # Metadata 1.0 - PEP 241
    metadata_version: str
    name: str
    version: str
    platforms: list[str]
    summary: str
    description: str
    keywords: list[str]
    home_page: str
    author: str
    author_email: str
    license: str

    # Metadata 1.1 - PEP 314
    supported_platforms: list[str]
    download_url: str
    classifiers: list[str]
    requires: list[str]
    provides: list[str]
    obsoletes: list[str]

    # Metadata 1.2 - PEP 345
    maintainer: str
    maintainer_email: str
    requires_dist: list[str]
    provides_dist: list[str]
    obsoletes_dist: list[str]
    requires_python: str
    requires_external: list[str]
    project_urls: dict[str, str]

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
    provides_extra: list[str]

    # Metadata 2.2 - PEP 643
    dynamic: list[str]

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

# General helper functions for parsing some string values for reusing in
# multiple parse_FORMAT functions


def _parse_keywords(data: str) -> list[str]:
    return [k.strip() for k in data.split(",")]


def _parse_project_urls(data: list[str]) -> dict[str, str]:
    urls = {}
    for pair in data:
        # Our logic is slightly tricky here as we want to try and do
        # *something* reasonable with malformed data.
        #
        # The main thing that we have to worry about, is data that does
        # not have a ',' at all to split the Key from the Value. There
        # isn't a singular right answer here, and we will fail validation
        # later on (if the caller is validating) so it doesn't *really*
        # matter, but since the missing value has to be an empty str
        # and our return value is dict[str, str], if we let the key
        # be the missing value, then they'd just multiple '' values that
        # overwrite each other.
        #
        # The other potentional issue is that it's possible to have the
        # same Key multiple times in the metadata, with no solid "right"
        # answer with what to do in that case, we'll do the only thing
        # we can, which is treat the field as unparseable and add it
        # to our list of unparsed fields.
        parts = [p.strip() for p in pair.split(",", 1)]
        parts.extend([""] * (max(0, 2 - len(parts))))  # Ensure 2 items

        # TODO: The spec doesn't say anything about if the keys should be
        #       considered case sensitive or not... logically they should
        #       be case preserving, but case insensitive, but doing that
        #       would open up more cases where we might have duplicated
        #       entries.
        label, url = parts
        if label in urls:
            # The label already exists in our set of urls, so this field
            # is unparseable, and we can just add the whole thing to our
            # unparseable data and stop processing it.
            raise KeyError("duplicate keys in project urls")
        urls[label] = url

    return urls


# The various parse_FORMAT functions here are intended to be as lenient as
# possible in their parsing, while still returning a correctly typed
# RawMetadata.
#
# To aid in this, we also generally want to do as little touching of the
# data as possible, except where there are possibly some historic holdovers
# that make valid data awkward to work with.
#
# While this is a lower level, intermediate format than our ``Metadata``
# class, some light touch ups can make a massive different in usability.


_EMAIL_FIELD_MAPPING = {
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


def parse_email(data: Union[bytes, str]) -> tuple[RawMetadata, dict[Any, Any]]:
    raw: dict[str, Any] = {}
    unparsed: dict[Any, Any] = {}

    if isinstance(data, str):
        parsed = email.parser.Parser(policy=email.policy.compat32).parsestr(data)
    else:
        parsed = email.parser.BytesParser(policy=email.policy.compat32).parsebytes(data)

    # We have to wrap parsed.keys() in a set, because in the case of multiple
    # values for a key (a list), the key will appear multiple times in the
    # list of keys, but we're avoiding that by using get_all().
    for name in set(parsed.keys()):
        # Header names in RFC are case insensitive, so we'll normalize to all
        # lower case to make comparisons easier.
        name = name.lower()

        # We use get_all here, even for fields that aren't multiple use, because
        # otherwise someone could have say, two Name fields, and we would just
        # silently ignore it rather than doing something about it.
        headers = parsed.get_all(name)

        # The way the email module works when parsing bytes is that it
        # unconditionally decodes the bytes as ascii, using the surrogateescape
        # handler, and then when you pull that data back out (such as with get_all)
        # it looks to see if the str has any surrogate escapes, and if it does
        # it wraps it in a Header object instead of returning the string.
        #
        # So we'll look for those Header objects, and fix up the encoding
        value = []
        valid_encoding = True
        for h in headers:
            # It's unclear if this can return more types than just a Header or
            # a str, so we'll just assert here to make sure.
            assert isinstance(h, (email.header.Header, str))

            # If it's a header object, we need to do our little dance to get
            # the real data out of it. In cases where there is invalid data
            # we're going to end up with mojibake, but I don't see a good way
            # around that without reimplementing parts of the Header object
            # ourselves.
            #
            # That should be fine, since if that happens, this key is going
            # into the unparsed dict anyways.
            if isinstance(h, email.header.Header):
                # The Heade object stores it's data as chunks, and each chunk
                # can be independently encoded, so we'll need to check each
                # of them.
                chunks = []
                for bin, encoding in email.header.decode_header(h):
                    # This means it found a surrogate escape, that could be
                    # valid data (if the source was utf8), or invalid.
                    if encoding == "unknown-8bit":
                        try:
                            bin.decode("utf8", "strict")
                        except UnicodeDecodeError:
                            # Enable mojibake
                            encoding = "latin1"
                            valid_encoding = False
                        else:
                            encoding = "utf8"
                    chunks.append((bin, encoding))

                # Turn our chunks back into a Header object, then let that
                # Header object do the right thing to turn them into a
                # string for us.
                value.append(str(email.header.make_header(chunks)))
            # This is already a string, so just add it
            else:
                value.append(h)

        # We've processed all of our values to get them into a list of str,
        # but we may have mojibake data, in which case this is an unparsed
        # field.
        if not valid_encoding:
            unparsed[name] = value
            continue

        raw_name = _EMAIL_FIELD_MAPPING.get(name)
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
        # value is a list of a single item, if it is then we'll assume that
        # it was emited as a single string, and unwrap the str from inside
        # the list.
        #
        # If it's any other kind of data, then we haven't the faintest clue
        # what we should parse it as, and we have to just add it to our list
        # of unparsed stuff.
        if raw_name in _STRING_FIELDS and len(value) == 1:
            raw[raw_name] = value[0]
        # If this is one our list of string fields, then we can just assign
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
        # specially formatted strings that represent a key and a value, which
        # is fundamentally a mapping, however the email format doesn't support
        # mappings in a sane way, so it was crammed into a list of strings
        # instead.
        #
        # We will do a little light data massaging to turn this into a map as
        # it logically should be.
        elif raw_name == "project_urls":
            try:
                raw[raw_name] = _parse_project_urls(value)
            except ValueError:
                unparsed[name] = value
        # Nothing that we've done has managed to parse this, so it'll just
        # throw it in our unparseable data and move on.
        else:
            unparsed[name] = value

    # We need to support getting the Description from the message payload in
    # addition to getting it from the the headers, but since Description is
    # conceptually a string, if it's already been set from headers then we'll
    # clear it out move them both to unparsed.
    try:
        payload = _get_payload(parsed, data)
    except ValueError:
        unparsed["Description"] = parsed.get_payload(decode=isinstance(data, bytes))
    else:
        # Check to see if we've already got a description, if so then both
        # it, and this body move to unparseable.
        if "description" in raw:
            unparsed["Description"] = [raw.pop("description"), payload]
        else:
            raw["description"] = payload

    # We need to cast our `raw` to a metadata, because a TypedDict only support
    # literal key names, but we're computing our key names on purpose, but the
    # way this function is implemented, our `TypedDict` can only have valid key
    # names.
    return cast(RawMetadata, raw), unparsed


# This might appear to be a mapping of the same key to itself, and in many cases
# it is. However, the algorithm in PEP 566 doesn't match 100% the keys chosen
# for RawMetadata, so we use this mapping just like with email to handle that.
_JSON_FIELD_MAPPING = {
    "author": "author",
    "author_email": "author_email",
    "classifier": "classifiers",
    "description": "description",
    "description_content_type": "description_content_type",
    "download_url": "download_url",
    "dynamic": "dynamic",
    "home_page": "home_page",
    "keywords": "keywords",
    "license": "license",
    "maintainer": "maintainer",
    "maintainer_email": "maintainer_email",
    "metadata_version": "metadata_version",
    "name": "name",
    "obsoletes": "obsoletes",
    "obsoletes_dist": "obsoletes_dist",
    "platform": "platforms",
    "project_url": "project_urls",
    "provides": "provides",
    "provides_dist": "provides_dist",
    "provides_extra": "provides_extra",
    "requires": "requires",
    "requires_dist": "requires_dist",
    "requires_external": "requires_external",
    "requires_python": "requires_python",
    "summary": "summary",
    "supported_platform": "supported_platforms",
    "version": "version",
}


def parse_json(data: Union[bytes, str]) -> tuple[RawMetadata, dict[Any, Any]]:
    raw: dict[Any, Any] = {}
    unparsed: dict[Any, Any] = {}
    parsed = json.loads(data)

    # We need to make sure that the data given to us actually implements
    # a dict, if it's any other type then there is no way we can parse
    # anything meaningful out of it, so we'll just give up and bail out.
    if not isinstance(parsed, dict):
        raise ValueError("Invalid json data, must be a mapping")

    for name, value in parsed.items():
        raw_name = _JSON_FIELD_MAPPING.get(name)
        if raw_name is None:
            # We don't know this key, so chuck it into our unparsed data
            # and continue on.
            unparsed[name] = value
            continue

        # If this is one of our string fields, check to see if it's actually
        # a string, if it's not then we don't have any idea how to handle it
        if raw_name in _STRING_FIELDS and isinstance(value, str):
            raw[raw_name] = value
        # If this is one of our string fields, check to see if it's actually
        # a list of strings, if it's not then we don't have any idea how to
        # handle it
        elif (
            raw_name in _LIST_STRING_FIELDS
            and isinstance(value, list)
            and all(isinstance(v, str) for v in value)
        ):
            raw[raw_name] = cast(list[str], value)
        # Special Case: Keywords
        # The keywords field is implemented in the metadata spec as a str,
        # but it conceptually is a list of strings. Interestingly, the
        # JSON spec as described in PEP 566 already implements this as a
        # list of strings, so we don't technically have to do anything.
        #
        # We're still treating this as as a special case though, because
        # in the metadata specification it's a single string, so it's not
        # included in our list of list string fields.
        elif (
            raw_name == "keywords"
            and isinstance(value, list)
            and all(isinstance(v, str) for v in value)
        ):
            raw[raw_name] = value
        # Special Case: Project-URL
        # The project urls is implemented in the metadata spec as a list of
        # specially formatted strings that represent a key and a value, which
        # is fundamentally a mapping, however the email format doesn't support
        # mappings in a sane way, so it was crammed into a list of strings
        # instead.
        #
        # We will do a little light data massaging to turn this into a map as
        # it logically should be.
        elif (
            raw_name == "project_urls"
            and isinstance(value, list)
            and all(isinstance(v, str) for v in value)
        ):
            try:
                raw[raw_name] = _parse_project_urls(value)
            except ValueError:
                unparsed[name] = value
        # Nothing that we've done has managed to parse this, so it'll just
        # throw it in our unparseable data and move on.
        else:
            unparsed[name] = value

    # We need to cast our `raw` to a metadata, because a TypedDict only support
    # literal key names, but we're computing our key names on purpose, but the
    # way this function is implemented, our `TypedDict` can only have valid key
    # names.
    return cast(RawMetadata, raw), unparsed


def _get_payload(msg: email.message.Message, source: Union[bytes, str]) -> str:
    # If our source is a str, then our caller has managed encodings for us,
    # and we don't need to deal with it.
    if isinstance(source, str):
        payload: Union[list[str], str] = msg.get_payload()
        if isinstance(payload, list):
            raise ValueError("payload is a multipart")
        return payload
    # If our source is a bytes, then we're managing the encoding and we need
    # to deal with it.
    else:
        bpayload: Union[list[bytes], bytes] = msg.get_payload(decode=True)
        if isinstance(bpayload, list):
            raise ValueError("payload is a multipart")

        try:
            return bpayload.decode("utf8", "strict")
        except UnicodeDecodeError:
            raise ValueError("payload in an invalid encoding")
