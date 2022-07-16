import email.feedparser
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
    metadata_version: str
    name: str
    version: str
    dynamic: list[str]
    platforms: list[str]
    supported_platforms: list[str]
    summary: str
    description: str
    description_content_type: str
    keywords: list[str]
    home_page: str
    download_url: str
    author: str
    author_email: str
    maintainer: str
    maintainer_email: str
    license: str
    classifiers: list[str]
    requires_dist: list[str]
    requires_python: str
    requires_external: list[str]
    project_urls: dict[str, str]
    provides_extra: list[str]
    provides_dist: list[str]
    obsoletes_dist: list[str]


_STRING_FIELDS = {
    "metadata_version",
    "name",
    "version",
    "summary",
    "home_page",
    "download_url",
    "author",
    "author_email",
    "maintainer",
    "maintainer_email",
    "license",
    "requires_python",
}

_LIST_STRING_FIELDS = {
    "dynamic",
    "platforms",
    "supported_platforms",
    "classifiers",
    "requires_dist",
    "requires_python",
    "requires_external",
    "provides_extra",
    "provides_dist",
    "obsoletes_dist",
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
    "Metadata-Version": "metadata_version",
    "Name": "name",
    "Version": "version",
    "Dynamic": "dynamic",
    "Platform": "platforms",
    "Supported-Platform": "supported_platforms",
    "Summary": "summary",
    "Description": "description",
    "Description-Content-Type": "description_content_type",
    "Keywords": "keywords",
    "Home-Page": "home_page",
    "Download-URL": "download_url",
    "Author": "author",
    "Author-Email": "author_email",
    "Maintainer": "maintainer",
    "Maintainer-Email": "maintainer_email",
    "License": "license",
    "Classifier": "classifiers",
    "Requires-Dist": "requires_dist",
    "Requires-Python": "requires_python",
    "Requires-External": "requires_external",
    "Project-URL": "project_urls",
    "Provides-Extra": "provides_extra",
    "Provides-Dist": "provides_dist",
    "Obsoletes-Dist": "obsoletes_dist",
}


def parse_email(data: Union[bytes, str]) -> tuple[RawMetadata, dict[Any, Any]]:
    raw = {}
    unparsed: dict[Any, Any] = {}

    if isinstance(data, str):
        parsed = email.parser.Parser(policy=email.policy.compat32).parsestr(data)
    else:
        # In theory we could use the BytesParser from email.parser, but that has
        # several problems that this method solves:
        #
        # 1. BytesParser (and BytesFeedParser) hard codes an assumption that the
        #    bytes are encoded as ascii (with a surrogateescape handler), but
        #    the packaging specifications explicitly have decided that our specs
        #    are in UTF8, not ascii.
        # 2. We could work around (1) by just decoding the bytes using utf8 ourself
        #    and then pass it into Parser, which we *could* do, however we're
        #    attempting to be lenient with this method to enable someone to usee
        #    this class to parse as much as possible while ignoring any errors that
        #    do come from it.
        #
        #    So we'll want to break our bytes up into a list of headers followed up
        #    by the message body.
        #
        #    Unfortunately, doing this is impossible without lightly parsing the
        #    RFC 822 format ourselves, which is not the most straightforward thing
        #    primarily because of a few concerns:
        #
        #    1. Conceptually RFC 822 messages is a format where you emit all of the
        #       headers first, one per line, then a blank line, then the body of the
        #       message. But it has the ability to "fold" a long header line across
        #       multiple lines, so to correctly do decoding on a field by field basis
        #       we will have to take this folding into account (but we do not need to
        #       actually implement the unfolding, we just want to make sure we have
        #       the entire logical "line" for that header).
        #    2. The message body isn't part of a normal field, it's effectively a
        #       a blank header field, then everythig else is part of the body.
        #    3. If a particular field can't be decoded using utf8, then we want to
        #       treat that field as unparseable, but getting the name out of that field
        #       requires implementing (more) of RFC 822 ourselves, though it's a pretty
        #       straight forward part.
        #    4. RFC 822 very specifically calls out CRLF as the line endings, but the
        #       python stdlib email.parser supports CRLF or LF, and in practice the
        #       core metadata specs are emiting METADATA files using LF only.
        #
        # TODO: Is doing this unconditionally for `bytes` the best idea here? Another
        #       option is to provide a helper function that will produce a possibly
        #       mojibaked string, and expect people who want per field decoding
        #       leniency to manually decode bytes using that method instead.
        parser = email.feedparser.FeedParser(policy=email.policy.compat32)

        # We don't use splitlines here, because it splits on a lot more different
        # types of line endings than we want to split on. Since in practice we
        # have to support just LF, we can just split on that, and do our decoding
        # and let the FeedParser deal with sorting out if it should be CRLF or LF.
        buf = b""
        in_body = False
        for line in data.split(b"\n"):
            # Put our LF back onto our line that the call to .split() removed.
            line = line + b"\n"

            # If we're in the body of our message, line continuation no longer matters
            # and we can just buffer the entire body so we can attempt to decode it
            # all at once.
            if in_body:
                buf += line
                continue

            # Continuation lines always start with LWSP, so we'll check to if we have
            # any data to parse and if so, if this is NOT a continuation line, if it's
            # not then we've finished reading the previous logical line, and we need
            # to decode it and pass it into the FeedParser.
            if buf and line[:1] not in {b" ", b"\t"}:
                try:
                    encoded = buf.decode("utf8", "strict")
                except UnicodeDecodeError:
                    # If we've gotten here, then we can't actually determine what
                    # encoding this line is in, so we'll try to pull a header key
                    # out of it to give us something to put into our unparsed data.
                    parts = buf.split(b":", 1)
                    parts.extend([b""] * (max(0, 2 - len(parts))))  # Ensure 2 items

                    # We're leaving this data as bytes and we're also leaving it folded,
                    # if the caller wants to attempt to parse something out of this
                    unparsed[parts[0]] = parts[1]
                else:
                    parser.feed(encoded)

                # Either way, this logical line has been handled, so we'll reset our
                # buffer and keep going.
                buf = b""

            # Check to see if this line is the "blank" line that signals the end
            # of the header data and the start of the body data.
            if line in {b"\n", b"\r\n"}:
                parser.feed(line.decode("utf8", "strict"))
                in_body = True
            # More header data, add it to our buffer
            else:
                buf += line

        # At this point, buf should be full of the entire body (if there was one) so
        # we'll attempt to decode that.
        try:
            encoded = buf.decode("utf8", "strict")
        except UnicodeDecodeError:
            # Our body isn't valid UTF8, we know what the key name for the Description
            # is though, so we can just use that
            unparsed["Description"] = buf

        # Actually consume our data, turning it into our email Message.
        parsed = parser.close()

    # We have to wrap parsed.keys() in a set, because in the case of multiple
    # values for a key (a list), the key will appear multiple times in the
    # list of keys, but we're avoiding that by using get_all().
    for name in set(parsed.keys()):
        # We use get_all here, even for fields that aren't multiple use, because
        # otherwise someone could have say, two Name fields, and we would just
        # silently ignore it rather than doing something about it.
        value = parsed.get_all(name)

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
    #
    # NOTE: For whatever reason, this will return a list of strings if the
    #       message is in mutlipart format, otherwise it will return a single
    #       string. The list format would be an unparseable error.
    payload = parsed.get_payload()
    if payload:
        # Check to see if we've got duplicated values, if so remove the
        # parsed one and move to unparsed.
        if "description" in raw:
            unparsed["Description"] = [raw.pop("description")]
            if isinstance(payload, str):
                unparsed["Description"].append(payload)
            else:
                unparsed["Description"].extend(payload)
        # If payload is a string, then we're good to go to add this to our
        # RawMetadata.
        elif isinstance(payload, str):
            raw["description"] = payload
        # Otherwise, it's unparseable, and we need to record that.
        else:
            unparsed["Description"] = payload

    # We need to cast our `raw` to a metadata, because a TypedDict only support
    # literal key names, but we're computing our key names on purpose, but the
    # way this function is implemented, our `TypedDict` can only have valid key
    # names.
    return cast(RawMetadata, raw), unparsed


# This might appear to be a mapping of the same key to itself, and in many cases
# it is. However, the algorithm in PEP 566 doesn't match 100% the keys chosen
# for RawMetadata, so we use this mapping just like with email to handle that.
_JSON_FIELD_MAPPING = {
    "metadata_version": "metadata_version",
    "name": "name",
    "version": "version",
    "dynamic": "dynamic",
    "platform": "platforms",
    "supported_platform": "supported_platforms",
    "summary": "summary",
    "description": "description",
    "description_content_type": "description_content_type",
    "keywords": "keywords",
    "home_page": "home_page",
    "download_url": "download_url",
    "author": "author",
    "author_email": "author_email",
    "maintainer": "maintainer",
    "maintainer_email": "maintainer_email",
    "license": "license",
    "classifier": "classifiers",
    "requires_dist": "requires_dist",
    "requires_python": "requires_python",
    "requires_external": "requires_external",
    "project_url": "project_urls",
    "provides_extra": "provides_extra",
    "provides_dist": "provides_dist",
    "obsoletes_dist": "obsoletes_dist",
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
