from __future__ import annotations

import re
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    Generic,
    List,
    Optional,
    Type,
    TypeVar,
    Union,
    cast,
)

if TYPE_CHECKING:
    from ._types import Metadata


V = TypeVar("V")


Validator = Callable[[V], None]


class lazy_validator(Generic[V]):

    # This hack exists to work around https://github.com/python/mypy/issues/708
    _creator: Union[Callable[[Any], V], Callable[[Any], V]]
    _raw_name: str
    _validators: List[Validator[Optional[V]]]

    def __init__(
        self,
        creator: Callable[[Any], V],
        *,
        raw_name: Optional[str] = None,
        validators: Optional[List[Validator[Optional[V]]]] = None,
    ) -> None:
        self._creator = creator
        if raw_name is not None:
            self._raw_name = raw_name
        if validators is not None:
            self._validators = validators
        else:
            self._validators = []

    def __set_name__(self, owner: Metadata, name: str) -> None:
        self._raw_name = name

    def __get__(self, obj: Metadata, owner: Type[Metadata]) -> Optional[V]:
        # TypedDict doesn't support variable key names, and Python 3.7 doesn't
        # support Literal which would let us let it know that this is validated
        # already to be safe, so we'll cast here to make things work.
        raw = cast(Dict[str, Any], obj._raw)
        validated = cast(Dict[str, Optional[V]], obj._validated)

        if self._raw_name not in validated:
            value = self._validate(raw.get(self._raw_name))
            validated[self._raw_name] = value
            del raw[self._raw_name]

        return validated[self._raw_name]

    def __set__(self, obj: Metadata, value: Any) -> None:
        raw = cast(Dict[str, Any], obj._raw)
        validated = cast(Dict[str, Optional[V]], obj._validated)

        validated_value = self._validate(value)
        validated[self._raw_name] = validated_value
        raw.pop(self._raw_name, None)

    def __delete__(self, obj: Metadata) -> None:
        raw = cast(Dict[str, Any], obj._raw)
        validated = cast(Dict[str, Optional[V]], obj._validated)

        raw.pop(self._raw_name, None)
        validated.pop(self._raw_name, None)

    def _validate(self, data: Any) -> Optional[V]:
        # Create our value from our raw data
        value = self._creator(data) if data is not None else None

        # Loop over our validators, and ensure that our value is actually valid
        for validator in self._validators:
            validator(value)

        return value


def eagerly_validate(obj: Metadata) -> None:
    for name, field in obj.__class__.__dict__.items():
        if isinstance(field, lazy_validator):
            getattr(obj, name)


class Required:

    _error_msg: str

    def __init__(self, message: Optional[str] = None):
        if message is None:
            self._error_msg = "value is required: {value!r}"
        else:
            self._error_msg = message

    def __call__(self, value: V) -> None:
        if value is None:
            raise ValueError(self._error_msg.format(value=value))


class RegexValidator:

    _regex: re.Pattern[str]
    _error_msg: str

    def __init__(
        self, regex: Union[str, re.Pattern[str]], *, message: Optional[str] = None
    ):
        if isinstance(regex, str):
            self._regex = re.compile(regex)
        else:
            self._regex = regex

        if message is None:
            self._error_msg = "invalid value: {value!r}"
        else:
            self._error_msg = message

    def __call__(self, value: Optional[str]) -> None:
        if value is not None and self._regex.search(value) is None:
            raise ValueError(self._error_msg.format(value=value))
