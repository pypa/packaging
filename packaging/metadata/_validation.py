from __future__ import annotations

import abc
import re
from typing import TYPE_CHECKING, Any, Callable, Dict, Generic, Optional, TypeVar, cast

if TYPE_CHECKING:
    from ._types import Metadata


T = TypeVar("T")


class lazy_validator(Generic[T]):  # noqa: N801

    # This hack exists to work around https://github.com/python/mypy/issues/708
    _creator: Callable[[Any], T] | Callable[[Any], T]
    _raw_name: str
    _validators: list[Callable[[Any], None]]

    def __init__(
        self,
        creator: Callable[[Any], T],
        *,
        raw_name: str | None = None,
        validators: list[Callable[[Any], None]] | None = None,
    ) -> None:
        self._creator = creator
        if raw_name is not None:
            self._raw_name = raw_name
        if validators is not None:
            self._validators = validators
        else:
            self._validators = []

    def __set_name__(self, owner: Metadata, name: str) -> None:
        if not hasattr(self, "_raw_name"):
            self._raw_name = name

    def __get__(self, obj: Metadata, owner: type[Metadata]) -> T | None:
        # TypedDict doesn't support variable key names, and Python 3.7 doesn't
        # support Literal which would let us let it know that this is validated
        # already to be safe, so we'll cast here to make things work.
        raw = cast(Dict[str, Any], obj._raw)
        validated = cast(Dict[str, Optional[T]], obj._validated)

        if self._raw_name not in validated:
            value = self._validate(raw.get(self._raw_name))
            validated[self._raw_name] = value
            del raw[self._raw_name]

        return validated[self._raw_name]

    def __set__(self, obj: Metadata, value: Any) -> None:
        raw = cast(Dict[str, Any], obj._raw)
        validated = cast(Dict[str, Optional[T]], obj._validated)

        validated_value = self._validate(value)
        validated[self._raw_name] = validated_value
        raw.pop(self._raw_name, None)

    def __delete__(self, obj: Metadata) -> None:
        raw = cast(Dict[str, Any], obj._raw)
        validated = cast(Dict[str, Optional[T]], obj._validated)

        raw.pop(self._raw_name, None)
        validated.pop(self._raw_name, None)

    def _validate(self, data: Any) -> T | None:
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


V = TypeVar("V")


class ValidationError(Exception):
    pass


class Validator(Generic[V], abc.ABC):

    message: str

    def __init__(self, *args: Any, message: str | None = None, **kwargs: Any):
        super().__init__(*args, **kwargs)
        if message is not None:
            self.message = message

    def __call__(self, value: V | None) -> None:
        try:
            self.full_validate(value)
        except Exception as exc:
            raise ValidationError(self.message.format(value=value)) from exc

    def full_validate(self, value: V | None) -> None:
        if value is not None:
            self.validate(value)

    @abc.abstractmethod
    def validate(self, value: V) -> None:
        ...


class Required(Validator[V]):

    message: str = "value is required: {value!r}"

    def full_validate(self, value: V | None) -> None:
        if value is None:
            raise ValueError("required value")

    def validate(self, value: V) -> None:
        pass


class RegexValidator(Validator[V]):

    _regex: re.Pattern[str]
    message: str = "invalid value: {value!r}"

    def __init__(self, regex: str | re.Pattern[str], *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)

        if isinstance(regex, str):
            self._regex = re.compile(regex)
        else:
            self._regex = regex

    def validate(self, value: V) -> None:
        if not isinstance(value, str):
            raise TypeError

        if self._regex.search(value) is None:
            raise ValueError(f"doesn't match: {self._regex.pattern}")


class SingleLine(Validator[V]):

    message: str = "must contain only one line: {value!r}"

    def validate(self, value: V) -> None:
        if not isinstance(value, str):
            raise TypeError

        if "\n" in value or "\r" in value:
            raise ValueError("multiline str")
