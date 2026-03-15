# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.
"""
.. testsetup::

    from packaging.specifiers import Specifier, SpecifierSet, InvalidSpecifier
    from packaging.version import Version
"""

from __future__ import annotations

import abc
import functools
import re
import typing
from typing import Any, Callable, Final, Iterable, Iterator, TypeVar, Union

from .utils import canonicalize_version
from .version import InvalidVersion, Version

__all__ = [
    "BaseSpecifier",
    "InvalidSpecifier",
    "Specifier",
    "SpecifierSet",
]


def __dir__() -> list[str]:
    return __all__


T = TypeVar("T")
UnparsedVersion = Union[Version, str]
UnparsedVersionVar = TypeVar("UnparsedVersionVar", bound=UnparsedVersion)


# The smallest possible PEP 440 version. No valid version is less than this.
_MIN_VERSION: Final[Version] = Version("0.dev0")


def _trim_release(release: tuple[int, ...]) -> tuple[int, ...]:
    """Strip trailing zeros from a release tuple for normalized comparison."""
    end = len(release)
    while end > 1 and release[end - 1] == 0:
        end -= 1
    return release if end == len(release) else release[:end]


# Sentinel kinds for _ExclusionBound.
_AFTER_LOCALS: Final[int] = 0  # sorts after V+local, before V.post0
_AFTER_POSTS: Final[int] = 1  # sorts after V.postN, before next release


@functools.total_ordering
class _ExclusionBound:
    """A synthetic bound that sorts between version families.

    PEP 440 has exclusion rules that can't be expressed with plain Version
    bounds. This sentinel encodes those rules into the version ordering so
    that interval arithmetic handles them correctly.

    ``_AFTER_LOCALS``: sorts after V and all V+local, before V.post0.
    Used for ``<=V``, ``==V``, ``!=V``, and ``>V.postN`` to correctly
    handle local versions.

    ``_AFTER_POSTS``: sorts after all V.postN (and V+local), before the
    next release segment. Used for ``>V`` (non-post) to exclude
    post-releases per PEP 440.

    Ordering for base version V::

        V < V+local < AFTER_LOCALS(V) < V.post0 < ... < AFTER_POSTS(V) < V.0.1
    """

    __slots__ = ("_kind", "_trimmed_release", "version")

    def __init__(self, version: Version, kind: int) -> None:
        self.version = version
        self._kind = kind
        self._trimmed_release = _trim_release(version.release)

    def _is_family(self, other: Version) -> bool:
        """Is ``other`` a version that this sentinel sorts above?"""
        v = self.version
        if not (
            other.epoch == v.epoch
            and _trim_release(other.release) == self._trimmed_release
            and other.pre == v.pre
        ):
            return False
        if self._kind == _AFTER_LOCALS:
            # Local family: exact same public version (any local label).
            return other.post == v.post and other.dev == v.dev
        # Post family: same base + any post-release (or identical).
        return other.dev == v.dev or other.post is not None

    def __eq__(self, other: object) -> bool:
        if isinstance(other, _ExclusionBound):
            return self.version == other.version and self._kind == other._kind
        return NotImplemented

    def __lt__(self, other: object) -> bool:
        if isinstance(other, _ExclusionBound):
            if self.version != other.version:
                return self.version < other.version
            return self._kind < other._kind
        assert isinstance(other, Version)
        # self < other iff other is NOT in the family and other > V
        return not self._is_family(other) and self.version < other

    def __hash__(self) -> int:
        return hash((self.version, self._kind))


if typing.TYPE_CHECKING:
    from typing_extensions import TypeAlias

    # Bound version: plain Version for most operators, _ExclusionBound
    # for bounds that encode PEP 440 exclusion rules, or None for unbounded.
    _BoundVersion: TypeAlias = Union[Version, _ExclusionBound, None]

    # A specifier bound: (bound_version, inclusive).
    _SpecifierBound: TypeAlias = tuple[_BoundVersion, bool]

    # A specifier interval: (lower_bound, upper_bound).
    _SpecifierInterval: TypeAlias = tuple[_SpecifierBound, _SpecifierBound]


_FULL_RANGE: list[_SpecifierInterval] = [((None, False), (None, False))]


def _spec_bound_lt(
    left: _SpecifierBound, right: _SpecifierBound, *, is_lower: bool
) -> bool:
    """Is bound ``left`` strictly less than bound ``right``?

    None represents -inf for lower bounds or +inf for upper bounds.
    When versions are equal, a tighter bound is "less": [v is tighter
    than (v for lower bounds, and (v is tighter than [v for upper bounds.
    """
    left_version, left_inclusive = left
    right_version, right_inclusive = right
    if left_version is None and right_version is None:
        return False
    if left_version is None:
        return is_lower  # -inf < anything for lower; +inf > anything for upper
    if right_version is None:
        return not is_lower  # anything < +inf for lower; anything > -inf for upper
    if left_version != right_version:
        return left_version < right_version
    # Same version: inclusive is tighter for lower, looser for upper.
    if is_lower:
        return left_inclusive and not right_inclusive
    return not left_inclusive and right_inclusive


def _intersect_intervals(
    left_intervals: list[_SpecifierInterval],
    right_intervals: list[_SpecifierInterval],
) -> list[_SpecifierInterval]:
    """Intersect two sorted, non-overlapping interval lists (two-pointer merge)."""
    result: list[_SpecifierInterval] = []
    left_index = right_index = 0
    while left_index < len(left_intervals) and right_index < len(right_intervals):
        left_lower, left_upper = left_intervals[left_index]
        right_lower, right_upper = right_intervals[right_index]

        # Take the tighter (higher) lower and tighter (lower) upper.
        lower = (
            right_lower
            if _spec_bound_lt(left_lower, right_lower, is_lower=True)
            else left_lower
        )
        upper = (
            left_upper
            if _spec_bound_lt(left_upper, right_upper, is_lower=False)
            else right_upper
        )

        # Only keep if the resulting interval is non-empty.
        lower_version, lower_inclusive = lower
        upper_version, upper_inclusive = upper
        if (
            lower_version is None
            or upper_version is None
            or lower_version < upper_version
            or (lower_version == upper_version and lower_inclusive and upper_inclusive)
        ):
            result.append((lower, upper))

        # Advance whichever side has the smaller upper bound.
        if _spec_bound_lt(left_upper, right_upper, is_lower=False):
            left_index += 1
        else:
            right_index += 1

    return result


def _filter_by_intervals(
    intervals: list[_SpecifierInterval],
    iterable: Iterable[Any],
    key: Callable[[Any], UnparsedVersion] | None,
    prereleases: bool,
) -> Iterator[Any]:
    """Filter versions against precomputed intervals.

    Local version segments are preserved on candidates; the interval bounds
    use :class:`_ExclusionBound` to handle local-version semantics.

    Used by both :class:`Specifier` and :class:`SpecifierSet`.
    Prerelease buffering (PEP 440 default) is NOT handled here;
    callers wrap the result with :func:`_pep440_filter_prereleases`
    when needed.
    """
    exclude_prereleases = prereleases is False

    for item in iterable:
        parsed = _coerce_version(item if key is None else key(item))
        if parsed is None:
            continue
        if exclude_prereleases and parsed.is_prerelease:
            continue
        # Check if version falls within any interval. Intervals are sorted
        # and non-overlapping, so at most one can match.
        for (lower_version, lower_inclusive), (
            upper_version,
            upper_inclusive,
        ) in intervals:
            if lower_version is not None and (
                parsed < lower_version
                or (parsed == lower_version and not lower_inclusive)
            ):
                break
            if (
                upper_version is None
                or parsed < upper_version
                or (parsed == upper_version and upper_inclusive)
            ):
                yield item
                break


def _pep440_filter_prereleases(
    iterable: Iterable[Any], key: Callable[[Any], UnparsedVersion] | None
) -> Iterator[Any]:
    """Filter per PEP 440: exclude prereleases unless no finals exist."""
    all_nonfinal: list[Any] = []
    arbitrary_strings: list[Any] = []

    found_final = False
    for item in iterable:
        parsed = _coerce_version(item if key is None else key(item))

        if parsed is None:
            # Arbitrary strings are always included as it is not
            # possible to determine if they are prereleases,
            # and they have already passed all specifiers.
            if found_final:
                yield item
            else:
                arbitrary_strings.append(item)
                all_nonfinal.append(item)
            continue

        if not parsed.is_prerelease:
            # Final release found: flush arbitrary strings, then yield
            if not found_final:
                yield from arbitrary_strings
                found_final = True
            yield item
            continue

        # Prerelease: buffer if no finals yet, otherwise skip
        if not found_final:
            all_nonfinal.append(item)

    # No finals found: yield all buffered items
    if not found_final:
        yield from all_nonfinal


def _coerce_version(version: UnparsedVersion) -> Version | None:
    if not isinstance(version, Version):
        try:
            version = Version(version)
        except InvalidVersion:
            return None
    return version


def _next_prefix_dev0(version: Version) -> Version:
    """Smallest version in the next prefix: 1.2 -> 1.3.dev0."""
    release = (*version.release[:-1], version.release[-1] + 1)
    return Version.from_parts(epoch=version.epoch, release=release, dev=0)


def _base_dev0(version: Version) -> Version:
    """The .dev0 of a version's base release: 1.2 -> 1.2.dev0."""
    return Version.from_parts(epoch=version.epoch, release=version.release, dev=0)


class InvalidSpecifier(ValueError):
    """
    Raised when attempting to create a :class:`Specifier` with a specifier
    string that is invalid.

    >>> Specifier("lolwat")
    Traceback (most recent call last):
        ...
    packaging.specifiers.InvalidSpecifier: Invalid specifier: 'lolwat'
    """


class BaseSpecifier(metaclass=abc.ABCMeta):
    __slots__ = ()
    __match_args__ = ("_str",)

    @property
    def _str(self) -> str:
        """Internal property for match_args"""
        return str(self)

    @abc.abstractmethod
    def __str__(self) -> str:
        """
        Returns the str representation of this Specifier-like object. This
        should be representative of the Specifier itself.
        """

    @abc.abstractmethod
    def __hash__(self) -> int:
        """
        Returns a hash value for this Specifier-like object.
        """

    @abc.abstractmethod
    def __eq__(self, other: object) -> bool:
        """
        Returns a boolean representing whether or not the two Specifier-like
        objects are equal.

        :param other: The other object to check against.
        """

    @property
    @abc.abstractmethod
    def prereleases(self) -> bool | None:
        """Whether or not pre-releases as a whole are allowed.

        This can be set to either ``True`` or ``False`` to explicitly enable or disable
        prereleases or it can be set to ``None`` (the default) to use default semantics.
        """

    @prereleases.setter  # noqa: B027
    def prereleases(self, value: bool) -> None:
        """Setter for :attr:`prereleases`.

        :param value: The value to set.
        """

    @abc.abstractmethod
    def contains(self, item: str, prereleases: bool | None = None) -> bool:
        """
        Determines if the given item is contained within this specifier.
        """

    @typing.overload
    def filter(
        self,
        iterable: Iterable[UnparsedVersionVar],
        prereleases: bool | None = None,
        key: None = ...,
    ) -> Iterator[UnparsedVersionVar]: ...

    @typing.overload
    def filter(
        self,
        iterable: Iterable[T],
        prereleases: bool | None = None,
        key: Callable[[T], UnparsedVersion] = ...,
    ) -> Iterator[T]: ...

    @abc.abstractmethod
    def filter(
        self,
        iterable: Iterable[Any],
        prereleases: bool | None = None,
        key: Callable[[Any], UnparsedVersion] | None = None,
    ) -> Iterator[Any]:
        """
        Takes an iterable of items and filters them so that only items which
        are contained within this specifier are allowed in it.
        """


class Specifier(BaseSpecifier):
    """This class abstracts handling of version specifiers.

    .. tip::

        It is generally not required to instantiate this manually. You should instead
        prefer to work with :class:`SpecifierSet` instead, which can parse
        comma-separated version specifiers (which is what package metadata contains).
    """

    __slots__ = (
        "_intervals",
        "_prereleases",
        "_spec",
        "_spec_version",
    )

    _specifier_regex_str = r"""
        (?:
            (?:
                # The identity operators allow for an escape hatch that will
                # do an exact string match of the version you wish to install.
                # This will not be parsed by PEP 440 and we cannot determine
                # any semantic meaning from it. This operator is discouraged
                # but included entirely as an escape hatch.
                ===  # Only match for the identity operator
                \s*
                [^\s;)]*  # The arbitrary version can be just about anything,
                          # we match everything except for whitespace, a
                          # semi-colon for marker support, and a closing paren
                          # since versions can be enclosed in them.
            )
            |
            (?:
                # The (non)equality operators allow for wild card and local
                # versions to be specified so we have to define these two
                # operators separately to enable that.
                (?:==|!=)            # Only match for equals and not equals

                \s*
                v?
                (?:[0-9]+!)?          # epoch
                [0-9]+(?:\.[0-9]+)*   # release

                # You cannot use a wild card and a pre-release, post-release, a dev or
                # local version together so group them with a | and make them optional.
                (?:
                    \.\*  # Wild card syntax of .*
                    |
                    (?a:                                  # pre release
                        [-_\.]?
                        (alpha|beta|preview|pre|a|b|c|rc)
                        [-_\.]?
                        [0-9]*
                    )?
                    (?a:                                  # post release
                        (?:-[0-9]+)|(?:[-_\.]?(post|rev|r)[-_\.]?[0-9]*)
                    )?
                    (?a:[-_\.]?dev[-_\.]?[0-9]*)?         # dev release
                    (?a:\+[a-z0-9]+(?:[-_\.][a-z0-9]+)*)? # local
                )?
            )
            |
            (?:
                # The compatible operator requires at least two digits in the
                # release segment.
                (?:~=)               # Only match for the compatible operator

                \s*
                v?
                (?:[0-9]+!)?          # epoch
                [0-9]+(?:\.[0-9]+)+   # release  (We have a + instead of a *)
                (?:                   # pre release
                    [-_\.]?
                    (alpha|beta|preview|pre|a|b|c|rc)
                    [-_\.]?
                    [0-9]*
                )?
                (?:                                   # post release
                    (?:-[0-9]+)|(?:[-_\.]?(post|rev|r)[-_\.]?[0-9]*)
                )?
                (?:[-_\.]?dev[-_\.]?[0-9]*)?          # dev release
            )
            |
            (?:
                # All other operators only allow a sub set of what the
                # (non)equality operators do. Specifically they do not allow
                # local versions to be specified nor do they allow the prefix
                # matching wild cards.
                (?:<=|>=|<|>)

                \s*
                v?
                (?:[0-9]+!)?          # epoch
                [0-9]+(?:\.[0-9]+)*   # release
                (?a:                   # pre release
                    [-_\.]?
                    (alpha|beta|preview|pre|a|b|c|rc)
                    [-_\.]?
                    [0-9]*
                )?
                (?a:                                   # post release
                    (?:-[0-9]+)|(?:[-_\.]?(post|rev|r)[-_\.]?[0-9]*)
                )?
                (?a:[-_\.]?dev[-_\.]?[0-9]*)?          # dev release
            )
        )
        """

    _regex = re.compile(
        r"\s*" + _specifier_regex_str + r"\s*", re.VERBOSE | re.IGNORECASE
    )

    def __init__(self, spec: str = "", prereleases: bool | None = None) -> None:
        """Initialize a Specifier instance.

        :param spec:
            The string representation of a specifier which will be parsed and
            normalized before use.
        :param prereleases:
            This tells the specifier if it should accept prerelease versions if
            applicable or not. The default of ``None`` will autodetect it from the
            given specifiers.
        :raises InvalidSpecifier:
            If the given specifier is invalid (i.e. bad syntax).
        """
        if not self._regex.fullmatch(spec):
            raise InvalidSpecifier(f"Invalid specifier: {spec!r}")

        spec = spec.strip()
        if spec.startswith("==="):
            operator, version = spec[:3], spec[3:].strip()
        elif spec.startswith(("~=", "==", "!=", "<=", ">=")):
            operator, version = spec[:2], spec[2:].strip()
        else:
            operator, version = spec[:1], spec[1:].strip()

        self._spec: tuple[str, str] = (operator, version)

        # Store whether or not this Specifier should accept prereleases
        self._prereleases = prereleases

        # Specifier version cache
        self._spec_version: tuple[str, Version] | None = None

        # Interval cache.
        self._intervals: list[_SpecifierInterval] | None = None

    def _get_spec_version(self, version: str) -> Version | None:
        """One element cache, as only one spec Version is needed per Specifier."""
        if self._spec_version is not None and self._spec_version[0] == version:
            return self._spec_version[1]

        version_specifier = _coerce_version(version)
        if version_specifier is None:
            return None

        self._spec_version = (version, version_specifier)
        return version_specifier

    def _require_spec_version(self, version: str) -> Version:
        """Get spec version, asserting it's valid (not for === operator).

        This method should only be called for operators where version
        strings are guaranteed to be valid PEP 440 versions (not ===).
        """
        spec_version = self._get_spec_version(version)
        assert spec_version is not None
        return spec_version

    def _to_intervals(self) -> list[_SpecifierInterval]:
        """Convert this specifier to sorted, non-overlapping intervals.

        Each standard operator maps to one or two intervals. The ``===``
        operator is modeled as full range since it uses arbitrary string
        matching; the actual check is done separately in ``filter()``.
        Result is cached.
        """
        if self._intervals is not None:
            return self._intervals

        op = self.operator
        ver_str = self.version

        if op == "===":
            self._intervals = _FULL_RANGE
            return _FULL_RANGE

        result: list[_SpecifierInterval]

        if ver_str.endswith(".*"):
            # Wildcard bounds: ==1.2.* matches [1.2.dev0, 1.3.dev0).
            base = self._require_spec_version(ver_str[:-2])
            lower = _base_dev0(base)
            upper = _next_prefix_dev0(base)
            if op == "==":
                result = [((lower, True), (upper, False))]
            else:  # !=
                result = [
                    ((None, False), (lower, False)),
                    ((upper, True), (None, False)),
                ]
        else:
            v = self._require_spec_version(ver_str)
            has_local = "+" in ver_str
            after_locals = _ExclusionBound(v, _AFTER_LOCALS)

            if op == ">=":
                result = [((v, True), (None, False))]
            elif op == "<=":
                # <=V matches V+local (PEP 440: local ignored).
                result = [((None, False), (after_locals, True))]
            elif op == ">":
                # >V must not match V+local or V.postN (when V is not
                # a post-release). Sentinels encode these exclusions.
                if v.is_postrelease:
                    result = [((after_locals, False), (None, False))]
                else:
                    result = [
                        (
                            (_ExclusionBound(v, _AFTER_POSTS), False),
                            (None, False),
                        )
                    ]
            elif op == "<":
                # <V excludes prereleases of V when V is not a prerelease,
                # so the effective upper bound is V.dev0.
                bound = v if v.is_prerelease else _base_dev0(v)
                if bound <= _MIN_VERSION:
                    result = []
                else:
                    result = [((None, False), (bound, False))]
            elif op == "==":
                # ==V (no local) matches V+local; ==V+local matches exactly.
                eq_upper: Version | _ExclusionBound = v if has_local else after_locals
                result = [((v, True), (eq_upper, True))]
            elif op == "!=":
                # !=V (no local) excludes V+local; !=V+local excludes exactly.
                ne_upper: Version | _ExclusionBound = v if has_local else after_locals
                result = [
                    ((None, False), (v, False)),
                    ((ne_upper, False), (None, False)),
                ]
            elif op == "~=":
                # ~=1.4.2 means >=1.4.2,<1.5.dev0
                prefix = v.__replace__(release=v.release[:-1])
                upper = _next_prefix_dev0(prefix)
                result = [((v, True), (upper, False))]
            else:
                raise ValueError(f"Unknown operator: {op!r}")  # pragma: no cover

        self._intervals = result
        return result

    @property
    def prereleases(self) -> bool | None:
        # If there is an explicit prereleases set for this, then we'll just
        # blindly use that.
        if self._prereleases is not None:
            return self._prereleases

        # Only the "!=" operator does not imply prereleases when
        # the version in the specifier is a prerelease.
        operator, version_str = self._spec
        if operator == "!=":
            return False

        # The == specifier with trailing .* cannot include prereleases
        # e.g. "==1.0a1.*" is not valid.
        if operator == "==" and version_str.endswith(".*"):
            return False

        # "===" can have arbitrary string versions, so we cannot parse
        # those, we take prereleases as unknown (None) for those.
        version = self._get_spec_version(version_str)
        if version is None:
            return None

        # For all other operators, use the check if spec Version
        # object implies pre-releases.
        return version.is_prerelease

    @prereleases.setter
    def prereleases(self, value: bool | None) -> None:
        self._prereleases = value

    @property
    def operator(self) -> str:
        """The operator of this specifier.

        >>> Specifier("==1.2.3").operator
        '=='
        """
        return self._spec[0]

    @property
    def version(self) -> str:
        """The version of this specifier.

        >>> Specifier("==1.2.3").version
        '1.2.3'
        """
        return self._spec[1]

    def __repr__(self) -> str:
        """A representation of the Specifier that shows all internal state.

        >>> Specifier('>=1.0.0')
        <Specifier('>=1.0.0')>
        >>> Specifier('>=1.0.0', prereleases=False)
        <Specifier('>=1.0.0', prereleases=False)>
        >>> Specifier('>=1.0.0', prereleases=True)
        <Specifier('>=1.0.0', prereleases=True)>
        """
        pre = (
            f", prereleases={self.prereleases!r}"
            if self._prereleases is not None
            else ""
        )

        return f"<{self.__class__.__name__}({str(self)!r}{pre})>"

    def __str__(self) -> str:
        """A string representation of the Specifier that can be round-tripped.

        >>> str(Specifier('>=1.0.0'))
        '>=1.0.0'
        >>> str(Specifier('>=1.0.0', prereleases=False))
        '>=1.0.0'
        """
        return "{}{}".format(*self._spec)

    @property
    def _canonical_spec(self) -> tuple[str, str]:
        operator, version = self._spec
        if operator == "===" or version.endswith(".*"):
            return operator, version

        spec_version = self._require_spec_version(version)

        canonical_version = canonicalize_version(
            spec_version, strip_trailing_zero=(operator != "~=")
        )

        return operator, canonical_version

    def __hash__(self) -> int:
        return hash(self._canonical_spec)

    def __eq__(self, other: object) -> bool:
        """Whether or not the two Specifier-like objects are equal.

        :param other: The other object to check against.

        The value of :attr:`prereleases` is ignored.

        >>> Specifier("==1.2.3") == Specifier("== 1.2.3.0")
        True
        >>> (Specifier("==1.2.3", prereleases=False) ==
        ...  Specifier("==1.2.3", prereleases=True))
        True
        >>> Specifier("==1.2.3") == "==1.2.3"
        True
        >>> Specifier("==1.2.3") == Specifier("==1.2.4")
        False
        >>> Specifier("==1.2.3") == Specifier("~=1.2.3")
        False
        """
        if isinstance(other, str):
            try:
                other = self.__class__(str(other))
            except InvalidSpecifier:
                return NotImplemented
        elif not isinstance(other, self.__class__):
            return NotImplemented

        return self._canonical_spec == other._canonical_spec

    def __contains__(self, item: str | Version) -> bool:
        """Return whether or not the item is contained in this specifier.

        :param item: The item to check for.

        This is used for the ``in`` operator and behaves the same as
        :meth:`contains` with no ``prereleases`` argument passed.

        >>> "1.2.3" in Specifier(">=1.2.3")
        True
        >>> Version("1.2.3") in Specifier(">=1.2.3")
        True
        >>> "1.0.0" in Specifier(">=1.2.3")
        False
        >>> "1.3.0a1" in Specifier(">=1.2.3")
        True
        >>> "1.3.0a1" in Specifier(">=1.2.3", prereleases=True)
        True
        """
        return self.contains(item)

    def contains(self, item: UnparsedVersion, prereleases: bool | None = None) -> bool:
        """Return whether or not the item is contained in this specifier.

        :param item:
            The item to check for, which can be a version string or a
            :class:`Version` instance.
        :param prereleases:
            Whether or not to match prereleases with this Specifier. If set to
            ``None`` (the default), it will follow the recommendation from
            :pep:`440` and match prereleases, as there are no other versions.

        >>> Specifier(">=1.2.3").contains("1.2.3")
        True
        >>> Specifier(">=1.2.3").contains(Version("1.2.3"))
        True
        >>> Specifier(">=1.2.3").contains("1.0.0")
        False
        >>> Specifier(">=1.2.3").contains("1.3.0a1")
        True
        >>> Specifier(">=1.2.3", prereleases=False).contains("1.3.0a1")
        False
        >>> Specifier(">=1.2.3").contains("1.3.0a1")
        True
        """

        return bool(list(self.filter([item], prereleases=prereleases)))

    @typing.overload
    def filter(
        self,
        iterable: Iterable[UnparsedVersionVar],
        prereleases: bool | None = None,
        key: None = ...,
    ) -> Iterator[UnparsedVersionVar]: ...

    @typing.overload
    def filter(
        self,
        iterable: Iterable[T],
        prereleases: bool | None = None,
        key: Callable[[T], UnparsedVersion] = ...,
    ) -> Iterator[T]: ...

    def filter(
        self,
        iterable: Iterable[Any],
        prereleases: bool | None = None,
        key: Callable[[Any], UnparsedVersion] | None = None,
    ) -> Iterator[Any]:
        """Filter items in the given iterable, that match the specifier.

        :param iterable:
            An iterable that can contain version strings and :class:`Version` instances.
            The items in the iterable will be filtered according to the specifier.
        :param prereleases:
            Whether or not to allow prereleases in the returned iterator. If set to
            ``None`` (the default), it will follow the recommendation from :pep:`440`
            and match prereleases if there are no other versions.
        :param key:
            A callable that takes a single argument (an item from the iterable) and
            returns a version string or :class:`Version` instance to be used for
            filtering.

        >>> list(Specifier(">=1.2.3").filter(["1.2", "1.3", "1.5a1"]))
        ['1.3']
        >>> list(Specifier(">=1.2.3").filter(["1.2", "1.2.3", "1.3", Version("1.4")]))
        ['1.2.3', '1.3', <Version('1.4')>]
        >>> list(Specifier(">=1.2.3").filter(["1.2", "1.5a1"]))
        ['1.5a1']
        >>> list(Specifier(">=1.2.3").filter(["1.3", "1.5a1"], prereleases=True))
        ['1.3', '1.5a1']
        >>> list(Specifier(">=1.2.3", prereleases=True).filter(["1.3", "1.5a1"]))
        ['1.3', '1.5a1']
        >>> list(Specifier(">=1.2.3").filter(
        ... [{"ver": "1.2"}, {"ver": "1.3"}],
        ... key=lambda x: x["ver"]))
        [{'ver': '1.3'}]
        """
        if self.operator == "===":
            # === uses arbitrary string matching, not version comparison.
            spec_str = self.version
            for item in iterable:
                raw = item if key is None else key(item)
                if str(raw).lower() == spec_str.lower():
                    yield item
            return

        # Determine concrete prerelease behavior, or leave as None
        # for PEP 440 default (include prereleases only if no finals exist).
        if prereleases is None:
            if self._prereleases is not None:
                prereleases = self._prereleases
            elif self.prereleases:
                prereleases = True

        # When prereleases is still None, pass True to include all versions
        # and let _pep440_filter_prereleases handle the buffering.
        resolve_pre = True if prereleases is None else prereleases

        filtered = _filter_by_intervals(
            self._to_intervals(),
            iterable,
            key,
            prereleases=resolve_pre,
        )

        if prereleases is not None:
            yield from filtered
        else:
            yield from _pep440_filter_prereleases(filtered, key)


class SpecifierSet(BaseSpecifier):
    """This class abstracts handling of a set of version specifiers.

    It can be passed a single specifier (``>=3.0``), a comma-separated list of
    specifiers (``>=3.0,!=3.1``), or no specifier at all.
    """

    __slots__ = (
        "_canonicalized",
        "_intervals",
        "_is_unsatisfiable",
        "_prereleases",
        "_specs",
    )

    def __init__(
        self,
        specifiers: str | Iterable[Specifier] = "",
        prereleases: bool | None = None,
    ) -> None:
        """Initialize a SpecifierSet instance.

        :param specifiers:
            The string representation of a specifier or a comma-separated list of
            specifiers which will be parsed and normalized before use.
            May also be an iterable of ``Specifier`` instances, which will be used
            as is.
        :param prereleases:
            This tells the SpecifierSet if it should accept prerelease versions if
            applicable or not. The default of ``None`` will autodetect it from the
            given specifiers.

        :raises InvalidSpecifier:
            If the given ``specifiers`` are not parseable than this exception will be
            raised.
        """

        if isinstance(specifiers, str):
            # Split on `,` to break each individual specifier into its own item, and
            # strip each item to remove leading/trailing whitespace.
            split_specifiers = [s.strip() for s in specifiers.split(",") if s.strip()]

            self._specs: tuple[Specifier, ...] = tuple(map(Specifier, split_specifiers))
        else:
            self._specs = tuple(specifiers)

        self._canonicalized = len(self._specs) <= 1
        self._is_unsatisfiable: bool | None = None
        self._intervals: list[_SpecifierInterval] | None = None

        # Store our prereleases value so we can use it later to determine if
        # we accept prereleases or not.
        self._prereleases = prereleases

    def _canonical_specs(self) -> tuple[Specifier, ...]:
        """Deduplicate, sort, and cache specs for order-sensitive operations."""
        if not self._canonicalized:
            self._specs = tuple(dict.fromkeys(sorted(self._specs, key=str)))
            self._canonicalized = True
            self._is_unsatisfiable = None
            self._intervals = None
        return self._specs

    @property
    def prereleases(self) -> bool | None:
        # If we have been given an explicit prerelease modifier, then we'll
        # pass that through here.
        if self._prereleases is not None:
            return self._prereleases

        # If we don't have any specifiers, and we don't have a forced value,
        # then we'll just return None since we don't know if this should have
        # pre-releases or not.
        if not self._specs:
            return None

        # Otherwise we'll see if any of the given specifiers accept
        # prereleases, if any of them do we'll return True, otherwise False.
        if any(s.prereleases for s in self._specs):
            return True

        return None

    @prereleases.setter
    def prereleases(self, value: bool | None) -> None:
        self._prereleases = value
        self._is_unsatisfiable = None
        self._intervals = None

    def __repr__(self) -> str:
        """A representation of the specifier set that shows all internal state.

        Note that the ordering of the individual specifiers within the set may not
        match the input string.

        >>> SpecifierSet('>=1.0.0,!=2.0.0')
        <SpecifierSet('!=2.0.0,>=1.0.0')>
        >>> SpecifierSet('>=1.0.0,!=2.0.0', prereleases=False)
        <SpecifierSet('!=2.0.0,>=1.0.0', prereleases=False)>
        >>> SpecifierSet('>=1.0.0,!=2.0.0', prereleases=True)
        <SpecifierSet('!=2.0.0,>=1.0.0', prereleases=True)>
        """
        pre = (
            f", prereleases={self.prereleases!r}"
            if self._prereleases is not None
            else ""
        )

        return f"<{self.__class__.__name__}({str(self)!r}{pre})>"

    def __str__(self) -> str:
        """A string representation of the specifier set that can be round-tripped.

        Note that the ordering of the individual specifiers within the set may not
        match the input string.

        >>> str(SpecifierSet(">=1.0.0,!=1.0.1"))
        '!=1.0.1,>=1.0.0'
        >>> str(SpecifierSet(">=1.0.0,!=1.0.1", prereleases=False))
        '!=1.0.1,>=1.0.0'
        """
        return ",".join(str(s) for s in self._canonical_specs())

    def __hash__(self) -> int:
        return hash(self._canonical_specs())

    def __and__(self, other: SpecifierSet | str) -> SpecifierSet:
        """Return a SpecifierSet which is a combination of the two sets.

        :param other: The other object to combine with.

        >>> SpecifierSet(">=1.0.0,!=1.0.1") & '<=2.0.0,!=2.0.1'
        <SpecifierSet('!=1.0.1,!=2.0.1,<=2.0.0,>=1.0.0')>
        >>> SpecifierSet(">=1.0.0,!=1.0.1") & SpecifierSet('<=2.0.0,!=2.0.1')
        <SpecifierSet('!=1.0.1,!=2.0.1,<=2.0.0,>=1.0.0')>
        """
        if isinstance(other, str):
            other = SpecifierSet(other)
        elif not isinstance(other, SpecifierSet):
            return NotImplemented

        specifier = SpecifierSet()
        specifier._specs = self._specs + other._specs
        specifier._canonicalized = len(specifier._specs) <= 1

        # Combine prerelease settings: use common or non-None value
        if self._prereleases is None or self._prereleases == other._prereleases:
            specifier._prereleases = other._prereleases
        elif other._prereleases is None:
            specifier._prereleases = self._prereleases
        else:
            raise ValueError(
                "Cannot combine SpecifierSets with True and False prerelease overrides."
            )

        return specifier

    def __eq__(self, other: object) -> bool:
        """Whether or not the two SpecifierSet-like objects are equal.

        :param other: The other object to check against.

        The value of :attr:`prereleases` is ignored.

        >>> SpecifierSet(">=1.0.0,!=1.0.1") == SpecifierSet(">=1.0.0,!=1.0.1")
        True
        >>> (SpecifierSet(">=1.0.0,!=1.0.1", prereleases=False) ==
        ...  SpecifierSet(">=1.0.0,!=1.0.1", prereleases=True))
        True
        >>> SpecifierSet(">=1.0.0,!=1.0.1") == ">=1.0.0,!=1.0.1"
        True
        >>> SpecifierSet(">=1.0.0,!=1.0.1") == SpecifierSet(">=1.0.0")
        False
        >>> SpecifierSet(">=1.0.0,!=1.0.1") == SpecifierSet(">=1.0.0,!=1.0.2")
        False
        """
        if isinstance(other, (str, Specifier)):
            other = SpecifierSet(str(other))
        elif not isinstance(other, SpecifierSet):
            return NotImplemented

        return self._canonical_specs() == other._canonical_specs()

    def __len__(self) -> int:
        """Returns the number of specifiers in this specifier set."""
        return len(self._specs)

    def __iter__(self) -> Iterator[Specifier]:
        """
        Returns an iterator over all the underlying :class:`Specifier` instances
        in this specifier set.

        >>> sorted(SpecifierSet(">=1.0.0,!=1.0.1"), key=str)
        [<Specifier('!=1.0.1')>, <Specifier('>=1.0.0')>]
        """
        return iter(self._specs)

    def _get_intervals(self) -> list[_SpecifierInterval] | None:
        """Compute and cache the intersected interval representation.

        Returns ``None`` if any spec uses ``===`` (arbitrary string matching
        that can't be modeled as version intervals).

        Returns an empty list if unsatisfiable, or the intersected interval
        list otherwise.
        """
        if self._intervals is not None:
            return self._intervals

        specs = self._specs

        # Intersect specs' intervals, bailing out if we encounter ===
        # (string matching, not version comparison) or if the intersection
        # becomes empty (unsatisfiable).
        result: list[_SpecifierInterval] | None = None
        for s in specs:
            if s.operator == "===":
                return None
            if result is None:
                result = s._to_intervals()
            else:
                result = _intersect_intervals(result, s._to_intervals())
                if not result:
                    break  # empty intersection, already unsatisfiable

        assert result is not None  # specs is non-empty
        self._intervals = result
        return result

    def is_unsatisfiable(self) -> bool:
        """Check whether this specifier set can never be satisfied.

        Returns True if no version can satisfy all specifiers simultaneously.
        Returns False if the set might be satisfiable (conservative: may
        return False for some unsatisfiable sets involving === specifiers).

        >>> SpecifierSet(">=2.0,<1.0").is_unsatisfiable()
        True
        >>> SpecifierSet(">=1.0,<2.0").is_unsatisfiable()
        False
        >>> SpecifierSet("").is_unsatisfiable()
        False
        >>> SpecifierSet("==1.0,!=1.0").is_unsatisfiable()
        True
        """
        cached = self._is_unsatisfiable
        if cached is not None:
            return cached

        if not self._specs:
            self._is_unsatisfiable = False
            return False

        intervals = self._get_intervals()
        if intervals is not None:
            # Standard specs: emptiness = unsatisfiable.
            result = not intervals
        else:
            # _get_intervals returned None (=== specs present).
            # Intervals are still valid for emptiness checking (=== is
            # modeled as full range, local bounds compare correctly);
            # it's only filtering that can't use them. Compute inline.
            computed = functools.reduce(
                _intersect_intervals,
                (s._to_intervals() for s in self._specs),
            )
            result = not computed

            # === with an unparsable version can only match raw strings,
            # but standard specs reject raw strings.
            if not result and any(
                s.operator == "===" and _coerce_version(s.version) is None
                for s in self._specs
            ):
                result = any(s.operator != "===" for s in self._specs)

        self._is_unsatisfiable = result
        return result

    def __contains__(self, item: UnparsedVersion) -> bool:
        """Return whether or not the item is contained in this specifier.

        :param item: The item to check for.

        This is used for the ``in`` operator and behaves the same as
        :meth:`contains` with no ``prereleases`` argument passed.

        >>> "1.2.3" in SpecifierSet(">=1.0.0,!=1.0.1")
        True
        >>> Version("1.2.3") in SpecifierSet(">=1.0.0,!=1.0.1")
        True
        >>> "1.0.1" in SpecifierSet(">=1.0.0,!=1.0.1")
        False
        >>> "1.3.0a1" in SpecifierSet(">=1.0.0,!=1.0.1")
        True
        >>> "1.3.0a1" in SpecifierSet(">=1.0.0,!=1.0.1", prereleases=True)
        True
        """
        return self.contains(item)

    def contains(
        self,
        item: UnparsedVersion,
        prereleases: bool | None = None,
        installed: bool | None = None,
    ) -> bool:
        """Return whether or not the item is contained in this SpecifierSet.

        :param item:
            The item to check for, which can be a version string or a
            :class:`Version` instance.
        :param prereleases:
            Whether or not to match prereleases with this SpecifierSet. If set to
            ``None`` (the default), it will follow the recommendation from :pep:`440`
            and match prereleases, as there are no other versions.
        :param installed:
            Whether or not the item is installed. If set to ``True``, it will
            accept prerelease versions even if the specifier does not allow them.

        >>> SpecifierSet(">=1.0.0,!=1.0.1").contains("1.2.3")
        True
        >>> SpecifierSet(">=1.0.0,!=1.0.1").contains(Version("1.2.3"))
        True
        >>> SpecifierSet(">=1.0.0,!=1.0.1").contains("1.0.1")
        False
        >>> SpecifierSet(">=1.0.0,!=1.0.1").contains("1.3.0a1")
        True
        >>> SpecifierSet(">=1.0.0,!=1.0.1", prereleases=False).contains("1.3.0a1")
        False
        >>> SpecifierSet(">=1.0.0,!=1.0.1").contains("1.3.0a1", prereleases=True)
        True
        """
        version = _coerce_version(item)

        if version is not None and installed and version.is_prerelease:
            prereleases = True

        check_item = item if version is None else version
        return bool(list(self.filter([check_item], prereleases=prereleases)))

    @typing.overload
    def filter(
        self,
        iterable: Iterable[UnparsedVersionVar],
        prereleases: bool | None = None,
        key: None = ...,
    ) -> Iterator[UnparsedVersionVar]: ...

    @typing.overload
    def filter(
        self,
        iterable: Iterable[T],
        prereleases: bool | None = None,
        key: Callable[[T], UnparsedVersion] = ...,
    ) -> Iterator[T]: ...

    def filter(
        self,
        iterable: Iterable[Any],
        prereleases: bool | None = None,
        key: Callable[[Any], UnparsedVersion] | None = None,
    ) -> Iterator[Any]:
        """Filter items in the given iterable, that match the specifiers in this set.

        :param iterable:
            An iterable that can contain version strings and :class:`Version` instances.
            The items in the iterable will be filtered according to the specifier.
        :param prereleases:
            Whether or not to allow prereleases in the returned iterator. If set to
            ``None`` (the default), it will follow the recommendation from :pep:`440`
            and match prereleases if there are no other versions.
        :param key:
            A callable that takes a single argument (an item from the iterable) and
            returns a version string or :class:`Version` instance to be used for
            filtering.

        >>> list(SpecifierSet(">=1.2.3").filter(["1.2", "1.3", "1.5a1"]))
        ['1.3']
        >>> list(SpecifierSet(">=1.2.3").filter(["1.2", "1.3", Version("1.4")]))
        ['1.3', <Version('1.4')>]
        >>> list(SpecifierSet(">=1.2.3").filter(["1.2", "1.5a1"]))
        ['1.5a1']
        >>> list(SpecifierSet(">=1.2.3").filter(["1.3", "1.5a1"], prereleases=True))
        ['1.3', '1.5a1']
        >>> list(SpecifierSet(">=1.2.3", prereleases=True).filter(["1.3", "1.5a1"]))
        ['1.3', '1.5a1']
        >>> list(SpecifierSet(">=1.2.3").filter(
        ... [{"ver": "1.2"}, {"ver": "1.3"}],
        ... key=lambda x: x["ver"]))
        [{'ver': '1.3'}]

        An "empty" SpecifierSet will filter items based on the presence of prerelease
        versions in the set.

        >>> list(SpecifierSet("").filter(["1.3", "1.5a1"]))
        ['1.3']
        >>> list(SpecifierSet("").filter(["1.5a1"]))
        ['1.5a1']
        >>> list(SpecifierSet("", prereleases=True).filter(["1.3", "1.5a1"]))
        ['1.3', '1.5a1']
        >>> list(SpecifierSet("").filter(["1.3", "1.5a1"], prereleases=True))
        ['1.3', '1.5a1']
        """
        # Determine if we're forcing a prerelease or not, if we're not forcing
        # one for this particular filter call, then we'll use whatever the
        # SpecifierSet thinks for whether or not we should support prereleases.
        if prereleases is None and self.prereleases is not None:
            prereleases = self.prereleases

        # Filter versions that match all specifiers.
        if self._specs:
            resolve_pre = True if prereleases is None else prereleases

            filtered: Iterator[Any]
            intervals = self._get_intervals()
            if intervals is not None:
                filtered = _filter_by_intervals(
                    intervals,
                    iterable,
                    key,
                    prereleases=resolve_pre,
                )
            else:
                # _get_intervals returns None when specs include ===
                # (arbitrary string matching, not version comparison).
                specs = self._specs
                filtered = (
                    item
                    for item in iterable
                    if all(
                        s.contains(
                            item if key is None else key(item),
                            prereleases=resolve_pre,
                        )
                        for s in specs
                    )
                )

            if prereleases is not None:
                return filtered

            return _pep440_filter_prereleases(filtered, key)

        # Handle Empty SpecifierSet.
        if prereleases is True:
            return iter(iterable)

        if prereleases is False:
            return (
                item
                for item in iterable
                if (
                    (version := _coerce_version(item if key is None else key(item)))
                    is None
                    or not version.is_prerelease
                )
            )

        # PEP 440: exclude prereleases unless no final releases matched
        return _pep440_filter_prereleases(iterable, key)
