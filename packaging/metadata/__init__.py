from email.parser import HeaderParser
from email.message import Message
from typing import Dict, Iterator, Union, List, Any
from typing_extensions import TypedDict
import inspect
import json
from .constants import VERSIONED_METADATA_FIELDS
import sys


def _json_form(val: str) -> str:
    return val.lower().replace("-", "_")


def _canonicalize(
    metadata: Dict[str, Union[List[str], str]]
) -> Dict[str, Union[List[str], str]]:
    """
    Transforms a metadata object to the canonical representation
    as specified in
    https://www.python.org/dev/peps/pep-0566/#json-compatible-metadata
    All transformed keys should be reduced to lower case. Hyphens
    should be replaced with underscores, but otherwise should retain all
    other characters.
    """
    return {_json_form(key): value for key, value in metadata.items()}


def check_python_compatability() -> None:
    if sys.version_info[0] < 3:
        raise ModuleNotFoundError()


check_python_compatability()


class Metadata:
    def __init__(self, **kwargs: Union[List[str], str]) -> None:
        self._meta_dict = kwargs

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Metadata):
            return self._meta_dict == other._meta_dict
        return NotImplemented

    @classmethod
    def from_json(cls, data: str) -> "Metadata":
        return cls(**_canonicalize(json.loads(data)))

    @classmethod
    def from_dict(cls, data: Dict[str, Union[List[str], str]]) -> "Metadata":
        return cls(**_canonicalize(data))

    @classmethod
    def from_rfc822(cls, rfc822_string: str) -> "Metadata":
        return cls(**Metadata._rfc822_string_to_dict(rfc822_string))

    def to_json(self) -> str:
        return json.dumps(self._meta_dict, sort_keys=True)

    def to_dict(self) -> Dict:
        return self._meta_dict

    def to_rfc822(self) -> str:
        msg = Message()
        metadata_version = self._meta_dict["metadata_version"]
        metadata_fields = VERSIONED_METADATA_FIELDS[metadata_version]
        for field in (
            metadata_fields["SINGLE"]
            | metadata_fields["MULTI"]
            | metadata_fields["TREAT_AS_MULTI"]
        ):
            value = self._meta_dict.get(_json_form(field))
            if value:
                if field == "Description":
                    # Special case - put in payload
                    msg.set_payload(value)
                    continue
                if field == "Keywords":
                    value = ",".join(value)
                if isinstance(value, str):
                    value = [value]
                for item in value:
                    msg.add_header(field, item)

        return msg.as_string()

    def __iter__(self) -> Iterator[Any]:
        return iter(self._meta_dict.items())

    @classmethod
    def _rfc822_string_to_dict(
        cls, rfc822_string: str
    ) -> Dict[str, Union[List[str], str]]:
        """Extracts metadata information from a metadata-version 2.1 object.

        https://www.python.org/dev/peps/pep-0566/#json-compatible-metadata

        - The original key-value format should be read with email.parser.HeaderParser;
        - All transformed keys should be reduced to lower case. Hyphens should
          be replaced with underscores, but otherwise should retain all other
          characters;
        - The transformed value for any field marked with "(Multiple-use")
          should be a single list containing all the original values for the
          given key;
        - The Keywords field should be converted to a list by splitting the
          original value on whitespace characters;
        - The message body, if present, should be set to the value of the
          description key.
        - The result should be stored as a string-keyed dictionary.
        """
        metadata: Dict[str, Union[List[str], str]] = {}
        parsed = HeaderParser().parsestr(rfc822_string)
        metadata_fields = VERSIONED_METADATA_FIELDS[parsed.get("Metadata-Version")]

        for key, value in parsed.items():
            if key in metadata_fields["MULTI"]:
                metadata.setdefault(key, []).append(value)
            elif key in metadata_fields["TREAT_AS_MULTI"]:
                metadata[key] = [val.strip() for val in value.split(",")]
            elif key == "Description":
                metadata[key] = inspect.cleandoc(value)
            else:
                metadata[key] = value

        # Handle the message payload
        payload = parsed.get_payload()
        if payload:
            if "Description" in metadata:
                print("Both Description and payload given - ignoring Description")
            metadata["Description"] = payload

        return _canonicalize(metadata)

    def validate(self) -> bool:
        raise NotImplementedError
