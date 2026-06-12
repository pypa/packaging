# This file is dual licensed under the terms of the Apache License, Version
# 2.0, and the BSD License. See the LICENSE file in the root of this repository
# for complete details.
"""
.. testsetup::

    from packaging.ranges import VersionRange
    from packaging.specifiers import Specifier, SpecifierSet, InvalidSpecifier
    from packaging.version import Version
"""

from __future__ import annotations

import abc
import copy
import re
import typing
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Final,
    Literal,
    TypeVar,
    Union,
)

from ._range_utils import (
    bounds_for_spec,
    filter_by_ranges,
    intersect_specifier_bounds,
    matches_bounds_only,
    ranges_are_prerelease_only,
    resolve_prereleases,
)
from ._version_utils import coerce_version, trim_release
from .ranges import VersionRange
from .utils import canonicalize_version
from .version import Version

if TYPE_CHECKING:
    import sys
    from collections.abc import Iterable, Iterator

    from ._range_utils import Interval

    if sys.version_info >= (3, 10):
        from typing import TypeGuard
    else:
        from typing_extensions import TypeGuard

__all__ = [
    "BaseSpecifier",
    "InvalidSpecifier",
    "Specifier",
    "SpecifierSet",
]


def __dir__() -> list[str]:
    return __all__


def _validate_spec(spec: object, /) -> TypeGuard[tuple[str, str]]:
    return (
        isinstance(spec, tuple)
        and len(spec) == 2
        and isinstance(spec[0], str)
        and isinstance(spec[1], str)
    )


def _validate_pre(pre: object, /) -> TypeGuard[bool | None]:
    return pre is None or isinstance(pre, bool)


T = TypeVar("T")
UnparsedVersion = Union[Version, str]
UnparsedVersionVar = TypeVar("UnparsedVersionVar", bound=UnparsedVersion)


def _direct_match(
    operator: str,
    spec_version: Version,
    parsed: Version,
) -> bool | None:
    """Direct comparison for a non-wildcard spec and a no-local ``parsed``.

    Returns the boolean match, or ``None`` when ``<``/``>`` lands inside V's
    pre/post/dev family and the range path is needed.
    """
    # ``<=``/``==``/``!=`` only reach here when parsed has no local segment
    # (PEP 440 strips locals on those); ``>=`` works regardless.
    if operator == ">=":
        return parsed >= spec_version
    if operator == "<=":
        return parsed <= spec_version
    if operator == "==":
        return parsed == spec_version
    if operator == "!=":
        return parsed != spec_version

    if operator in ("<", ">"):
        # ``<V``/``>V`` carve out V's family (pre/dev/post). A direct
        # comparison is correct only when parsed is outside that family.
        if parsed.epoch != spec_version.epoch or trim_release(
            parsed.release
        ) != trim_release(spec_version.release):
            return parsed < spec_version if operator == "<" else parsed > spec_version
        return None

    return None


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

        It is generally not required to instantiate this manually. You
        should instead prefer to work with
        :class:`~packaging.specifiers.SpecifierSet` instead, which can
        parse comma-separated version specifiers (which is what package
        metadata contains).

    Instances are safe to serialize with :mod:`pickle`. They use a stable
    format so the same pickle can be loaded in future packaging releases.

    .. versionchanged:: 26.2

        Added a stable pickle format. Pickles created with packaging 26.2+ can
        be unpickled with future releases.  Backward compatibility with pickles
        from packaging < 26.2 is supported but may be removed in a future
        release.
    """

    __slots__ = (
        "_prereleases",
        "_range_cache",
        "_range_cache_key",
        "_ranges",
        "_resolved_prereleases",
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

    # Legacy unused attribute, kept for backward compatibility
    _operators: Final = {
        "~=": "compatible",
        "==": "equal",
        "!=": "not_equal",
        "<=": "less_than_equal",
        ">=": "greater_than_equal",
        "<": "less_than",
        ">": "greater_than",
        "===": "arbitrary",
    }

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

        # VersionRange cache, populated by :meth:`to_range`.
        self._range_cache: VersionRange | None = None
        # Last-stamped ``(resolved, configured)`` pre-release tags for
        # :attr:`_range_cache`. Lets :meth:`to_range` detect a caller mutating
        # the cached range and hand back a fresh copy without re-running
        # ``from_specifier``.
        self._range_cache_key: tuple[bool | None, bool | None] | None = None

        # Internal bounds cache for the hot filter / contains path,
        # populated lazily by :meth:`_to_ranges`.
        self._ranges: tuple[Interval, ...] | None = None

        # Cache of the autodetected ``prereleases`` value; ``"unset"`` is a
        # sentinel because ``None`` is a valid resolved value.
        self._resolved_prereleases: bool | None | Literal["unset"] = "unset"

    def _get_spec_version(self, version: str) -> Version | None:
        """One element cache, as only one spec Version is needed per Specifier."""
        if self._spec_version is not None and self._spec_version[0] == version:
            return self._spec_version[1]

        version_specifier = coerce_version(version)
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

    def _to_ranges(self) -> tuple[Interval, ...]:
        """Per-instance cache around :func:`bounds_for_spec`.

        Only called for the non-``===`` operators; ``===`` filtering goes
        through :meth:`to_range`.
        """
        bounds = self._ranges
        if bounds is not None:
            return bounds

        op, ver_str = self._spec
        # Warm (and reuse) the per-instance parsed-version cache so siblings
        # like ``_fast_match`` and ``__hash__`` skip the re-parse later.
        # Wildcards cache the base ``X[.Y]*`` slice; everything else caches
        # ``ver_str``.
        parsed = self._require_spec_version(ver_str.removesuffix(".*"))
        bounds = bounds_for_spec(op, ver_str, parsed=parsed)
        self._ranges = bounds
        return bounds

    def _range_prereleases(self) -> tuple[bool | None, bool | None]:
        """Return the ``(resolved, configured)`` tag a
        :class:`~packaging.ranges.VersionRange` built from this object should carry.

        Configured is what was passed to ``__init__``; resolved folds the
        PEP 440 default into the autodetected value. Together they let the
        range mirror :meth:`filter` defaults and set-algebra behaviour.
        """
        return (
            resolve_prereleases(self._prereleases, self.prereleases),
            self._prereleases,
        )

    def _fast_match(self, parsed: Version) -> bool | None:
        """Match ``parsed`` against this specifier without building a range.

        Handles ``>=``, ``<=``, ``==``, ``!=``, ``<``, ``>`` when the spec
        is not a wildcard. A local segment on ``parsed`` is safe for ``>=``
        (locals only widen V's family upward, so the threshold answer is
        unchanged) but not for the others, which need the range path's
        local-stripping. Returns ``None`` when the range path must be used.
        Pre-release policy is left to the caller. Uses the per-instance
        parsed-version cache.
        """
        op_str, ver_str = self._spec
        if ver_str.endswith(".*"):
            return None
        if parsed.local is not None and op_str != ">=":
            return None
        return _direct_match(op_str, self._require_spec_version(ver_str), parsed)

    @property
    def prereleases(self) -> bool | None:
        # If there is an explicit prereleases set for this, then we'll just
        # blindly use that.
        if self._prereleases is not None:
            return self._prereleases

        cached = self._resolved_prereleases
        if cached != "unset":
            return cached

        # Only the "!=" operator does not imply prereleases when
        # the version in the specifier is a prerelease.
        operator, version_str = self._spec
        if operator == "!=":
            resolved: bool | None = False
        elif operator == "==" and version_str.endswith(".*"):
            # The == specifier with trailing .* cannot include prereleases
            # e.g. "==1.0a1.*" is not valid.
            resolved = False
        else:
            # "===" can have arbitrary string versions, so we cannot parse
            # those, we take prereleases as unknown (None) for those.
            version = self._get_spec_version(version_str)
            resolved = None if version is None else version.is_prerelease

        self._resolved_prereleases = resolved
        return resolved

    @prereleases.setter
    def prereleases(self, value: bool | None) -> None:
        self._prereleases = value
        # The range carries the resolved prereleases value, so drop the
        # cache; the bounds-only ``_ranges`` cache is unaffected.
        self._range_cache = None
        self._range_cache_key = None
        self._resolved_prereleases = "unset"

    def __getstate__(self) -> tuple[tuple[str, str], bool | None]:
        # Return state as a 2-item tuple for compactness:
        #   ((operator, version), prereleases)
        # Cache members are excluded and will be recomputed on demand.
        return (self._spec, self._prereleases)

    def __setstate__(self, state: object) -> None:
        # Always discard cached values - they will be recomputed on demand.
        self._spec_version = None
        self._range_cache = None
        self._range_cache_key = None
        self._ranges = None
        self._resolved_prereleases = "unset"

        if isinstance(state, tuple):
            if len(state) == 2:
                # New format (26.2+): ((operator, version), prereleases)
                spec, prereleases = state
                if _validate_spec(spec) and _validate_pre(prereleases):
                    self._spec = spec
                    self._prereleases = prereleases
                    return
            if len(state) == 2 and isinstance(state[1], dict):
                # Format (packaging 26.0-26.1): (None, {slot: value}).
                _, slot_dict = state
                spec = slot_dict.get("_spec")
                prereleases = slot_dict.get("_prereleases", "invalid")
                if _validate_spec(spec) and _validate_pre(prereleases):
                    self._spec = spec
                    self._prereleases = prereleases
                    return
        if isinstance(state, dict):
            # Old format (packaging <= 25.x, no __slots__): state is a plain dict.
            spec = state.get("_spec")
            prereleases = state.get("_prereleases", "invalid")
            if _validate_spec(spec) and _validate_pre(prereleases):
                self._spec = spec
                self._prereleases = prereleases
                return

        raise TypeError(f"Cannot restore Specifier from {state!r}")

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
            :class:`~packaging.version.Version` instance.
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

        :raises TypeError: if ``item`` is not a :class:`str` or
            :class:`~packaging.version.Version`.
        """
        if not isinstance(item, (str, Version)):
            raise TypeError(
                f"Specifier.contains() expected str or Version, "
                f"got {type(item).__name__}"
            )

        # ``===`` compares the raw string, so a Version parse here would
        # be wasted.
        if self._spec[0] == "===":
            return bool(list(self.filter([item], prereleases=prereleases)))

        parsed = coerce_version(item)
        if parsed is None:
            # Standard operators never match an unparsable input.
            return False

        match = self._fast_match(parsed)
        if match is not None:
            if prereleases is None:
                prereleases = resolve_prereleases(self._prereleases, self.prereleases)
            if prereleases is False and parsed.is_prerelease:
                return False
            return match

        # Pass the already-parsed Version so VersionRange.filter doesn't
        # re-coerce it.
        return bool(list(self.filter([parsed], prereleases=prereleases)))

    def to_range(self) -> VersionRange:
        """The :class:`~packaging.ranges.VersionRange` accepted by this
        specifier.

        For ``===`` the returned range matches the literal string
        case-insensitively; no PEP 440
        :class:`~packaging.version.Version` other than the literal
        itself is contained.

        >>> isinstance(Specifier(">=1.0").to_range(), VersionRange)
        True
        >>> "wat" in Specifier("===wat").to_range()
        True

        .. versionadded:: 26.3
        """
        cache = self._range_cache
        if cache is None or self._range_cache_key is None:
            cache = VersionRange.from_specifier(self)
            self._range_cache = cache
            self._range_cache_key = (cache._prereleases, cache._prereleases_configured)
            return cache

        # A caller may have mutated the cached range's tags after we handed
        # it out. If the captured stamp still matches, the cache is clean;
        # otherwise hand back a freshly stamped copy.
        resolved, configured = self._range_cache_key
        if (
            cache._prereleases == resolved
            and cache._prereleases_configured == configured
        ):
            return cache

        refreshed = copy.copy(cache)
        refreshed._restamp(resolved=resolved, configured=configured)
        self._range_cache = refreshed
        return refreshed

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
            An iterable that can contain version strings and
            :class:`~packaging.version.Version` instances. The items in the
            iterable will be filtered according to the specifier.
        :param prereleases:
            Whether or not to allow prereleases in the returned iterator. If set to
            ``None`` (the default), it will follow the recommendation from :pep:`440`
            and match prereleases if there are no other versions.
        :param key:
            A callable that takes a single argument (an item from the iterable) and
            returns a version string or :class:`~packaging.version.Version`
            instance to be used for filtering.

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

        .. versionchanged:: 26.1

            Added the ``key`` parameter.
        """
        # Resolve the default when no explicit value is given.
        if prereleases is None:
            prereleases = resolve_prereleases(self._prereleases, self.prereleases)
        # Non-``===`` specifiers go through the bounds-only fast path
        # (``packaging._range_utils`` is private; this is the only
        # back-channel into the range machinery that is not
        # :class:`VersionRange`'s public API). ``===`` keeps the
        # admission-aware :meth:`VersionRange.filter` path.
        if self._spec[0] != "===":
            return filter_by_ranges(
                ranges=self._to_ranges(),
                iterable=iterable,
                key=key,
                prereleases=prereleases,
            )

        return self.to_range().filter(iterable, key=key, prereleases=prereleases)


class SpecifierSet(BaseSpecifier):
    """This class abstracts handling of a set of version specifiers.

    It can be passed a single specifier (``>=3.0``), a comma-separated list of
    specifiers (``>=3.0,!=3.1``), or no specifier at all.

    Instances are safe to serialize with :mod:`pickle`. They use a stable
    format so the same pickle can be loaded in future packaging
    releases.

    .. versionchanged:: 26.2

        Added a stable pickle format. Pickles created with
        packaging 26.2+ can be unpickled with future releases.
        Backward compatibility with pickles from
        packaging < 26.2 is supported but may be removed in a future
        release.
    """

    __slots__ = (
        "_canonicalized",
        "_has_arbitrary",
        "_is_unsatisfiable",
        "_prereleases",
        "_range_cache",
        "_range_cache_key",
        "_ranges",
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
            split_specifiers = [s.strip() for s in specifiers.split(",") if s.strip()]
            self._specs: tuple[Specifier, ...] = tuple(map(Specifier, split_specifiers))
            # Fast substring check; avoids iterating parsed specs.
            self._has_arbitrary = "===" in specifiers
        else:
            self._specs = tuple(specifiers)
            # Substring check works for both Specifier objects and plain
            # strings (setuptools passes lists of strings).
            self._has_arbitrary = any("===" in str(s) for s in self._specs)

        self._canonicalized = len(self._specs) <= 1
        self._is_unsatisfiable: bool | None = None
        self._range_cache: VersionRange | None = None
        # Last-stamped policy for :attr:`_range_cache`: ``(configured,
        # resolved)`` captured when the cache was tagged. Lets the cached
        # path skip resolving :attr:`prereleases` live on each hit.
        self._range_cache_key: tuple[bool | None, bool | None] | None = None
        # Internal bounds cache for the hot filter path (populated by
        # :meth:`_intersect_bounds`). ``contains`` reads it when set but
        # never populates it, so a contains-only workload stays on the
        # per-spec path without paying the intersected-bounds build cost.
        self._ranges: tuple[Interval, ...] | None = None
        self._prereleases = prereleases

    def _canonical_specs(self) -> tuple[Specifier, ...]:
        """Deduplicate, sort, and cache specs for order-sensitive operations.

        Sort and dedup do not change the set of versions accepted by the set,
        so the cached bounds (``_ranges``), the cached range
        (``_range_cache``), and ``_is_unsatisfiable`` all stay valid. No
        invalidation here; touching them would just force a re-derivation
        with the same result.
        """
        if not self._canonicalized:
            self._specs = tuple(dict.fromkeys(sorted(self._specs, key=str)))
            self._canonicalized = True
        return self._specs

    def _range_prereleases(self) -> tuple[bool | None, bool | None]:
        """Return the ``(resolved, configured)`` tag a
        :class:`~packaging.ranges.VersionRange` built from this object should carry.

        A set's public ``prereleases`` already folds in the autodetected value
        and equals the resolved tag, so the configured tag is the only
        constructor flag the range needs to track separately. ``__and__``
        relies on the distinction to mirror its True/False conflict rule.
        """
        return self.prereleases, self._prereleases

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
        self._range_cache = None
        self._range_cache_key = None
        self._ranges = None

    def __getstate__(self) -> tuple[tuple[Specifier, ...], bool | None]:
        # Return state as a 2-item tuple for compactness:
        #   (specs, prereleases)
        # Cache members are excluded and will be recomputed on demand.
        return (self._specs, self._prereleases)

    def __setstate__(self, state: object) -> None:
        # Always discard cached values - they will be recomputed on demand.
        self._is_unsatisfiable = None
        self._range_cache = None
        self._range_cache_key = None
        self._ranges = None

        if isinstance(state, tuple):
            if len(state) == 2:
                # New format (26.2+): (specs, prereleases)
                specs, prereleases = state
                if (
                    isinstance(specs, tuple)
                    and all(isinstance(s, Specifier) for s in specs)
                    and _validate_pre(prereleases)
                ):
                    self._specs = specs
                    self._prereleases = prereleases
                    self._canonicalized = len(specs) <= 1
                    self._has_arbitrary = any("===" in str(s) for s in specs)
                    return
            if len(state) == 2 and isinstance(state[1], dict):
                # Format (packaging 26.0-26.1): (None, {slot: value}).
                _, slot_dict = state
                specs = slot_dict.get("_specs", ())
                prereleases = slot_dict.get("_prereleases")
                # Convert frozenset to tuple (26.0 stored as frozenset)
                if isinstance(specs, frozenset):
                    specs = tuple(sorted(specs, key=str))
                if (
                    isinstance(specs, tuple)
                    and all(isinstance(s, Specifier) for s in specs)
                    and _validate_pre(prereleases)
                ):
                    self._specs = specs
                    self._prereleases = prereleases
                    self._canonicalized = len(self._specs) <= 1
                    self._has_arbitrary = any("===" in str(s) for s in self._specs)
                    return
        if isinstance(state, dict):
            # Old format (packaging <= 25.x, no __slots__): state is a plain dict.
            specs = state.get("_specs", ())
            prereleases = state.get("_prereleases")
            # Convert frozenset to tuple (26.0 stored as frozenset)
            if isinstance(specs, frozenset):
                specs = tuple(sorted(specs, key=str))
            if (
                isinstance(specs, tuple)
                and all(isinstance(s, Specifier) for s in specs)
                and _validate_pre(prereleases)
            ):
                self._specs = specs
                self._prereleases = prereleases
                self._canonicalized = len(self._specs) <= 1
                self._has_arbitrary = any("===" in str(s) for s in self._specs)
                return

        raise TypeError(f"Cannot restore SpecifierSet from {state!r}")

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
        specifier._has_arbitrary = self._has_arbitrary or other._has_arbitrary

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

    def is_unsatisfiable(self) -> bool:
        """Check whether this specifier set can never be satisfied.

        Returns True if no version can satisfy all specifiers simultaneously.

        >>> SpecifierSet(">=2.0,<1.0").is_unsatisfiable()
        True
        >>> SpecifierSet(">=1.0,<2.0").is_unsatisfiable()
        False
        >>> SpecifierSet("").is_unsatisfiable()
        False
        >>> SpecifierSet("==1.0,!=1.0").is_unsatisfiable()
        True

        .. versionadded:: 26.1
        """
        cached = self._is_unsatisfiable
        if cached is not None:
            return cached

        if not self._specs:
            self._is_unsatisfiable = False
            return False

        # ``===`` introduces literal-string matching that bare bounds can't
        # represent, so route those through the full VersionRange.
        if self._has_arbitrary:
            range_ = self.to_range()

            if range_.is_empty:
                self._is_unsatisfiable = True
                return True
            if self.prereleases is not False:
                self._is_unsatisfiable = False
                return False

            result = range_.is_prerelease_only
            self._is_unsatisfiable = result
            return result

        # Bounds-only fast path: reuse each Specifier's cached intervals
        # instead of folding via VersionRange.from_specifier.
        if (bounds := self._ranges) is None:
            bounds = self._ranges = self._intersect_bounds()

        if not bounds:
            self._is_unsatisfiable = True
            return True
        if self.prereleases is not False:
            self._is_unsatisfiable = False
            return False

        result = ranges_are_prerelease_only(bounds)
        self._is_unsatisfiable = result
        return result

    def to_range(self) -> VersionRange:
        """The :class:`~packaging.ranges.VersionRange` accepted by this
        specifier set.

        The intersection of every specifier in the set. An empty
        :class:`~packaging.specifiers.SpecifierSet` yields the
        unbounded range; an unsatisfiable set yields an empty
        :class:`~packaging.ranges.VersionRange`. Sets containing
        ``===`` produce a range whose only matching items are the
        literal strings (case-insensitive) that satisfy every
        rangelike specifier in the set as well.

        >>> isinstance(SpecifierSet(">=1.0,<2.0").to_range(), VersionRange)
        True
        >>> SpecifierSet(">=1.0,<2.0").to_range().is_empty
        False
        >>> SpecifierSet(">=2.0,<1.0").to_range().is_empty
        True
        >>> "wat" in SpecifierSet("===wat").to_range()
        True

        .. versionadded:: 26.3
        """
        cache = self._range_cache
        if cache is None or self._range_cache_key is None:
            cache = VersionRange.from_specifier_set(self)
            self._range_cache = cache
            self._range_cache_key = (cache._prereleases, cache._prereleases_configured)
            return cache

        # Two drift sources to catch. (1) A caller mutated the cached range's
        # tags after we handed it out; (2) an inner Specifier's ``prereleases``
        # changed under us, shifting the set's autodetect without going
        # through this set's setter (which would have cleared the cache).
        # Either way, hand back a freshly stamped copy rather than re-stamping
        # the range an earlier call returned. The structural bounds are
        # policy-independent so only the carried tags need updating.
        resolved_stamped, configured_stamped = self._range_cache_key
        if (
            cache._prereleases == resolved_stamped
            and cache._prereleases_configured == configured_stamped
            and (configured_stamped is not None or self.prereleases == resolved_stamped)
        ):
            return cache

        # ``_restamp`` is :class:`~packaging.ranges.VersionRange`'s friend API
        # for this ranges<->specifiers cache-refresh path; the slots have no
        # public setter by design.
        resolved = (
            resolved_stamped if configured_stamped is not None else self.prereleases
        )
        refreshed = copy.copy(cache)
        refreshed._restamp(resolved=resolved, configured=configured_stamped)
        self._range_cache = refreshed
        self._range_cache_key = (resolved, configured_stamped)
        return refreshed

    def _intersect_bounds(self) -> tuple[Interval, ...]:
        """Intersect every specifier's bounds into a single range.

        Thin wrapper that reuses each :class:`Specifier`'s per-instance bounds
        cache and folds via :func:`intersect_specifier_bounds`. Callers must
        exclude ``===`` specifiers (which have no bound form) and guard
        against the empty set; the result feeds :meth:`is_unsatisfiable` and
        the cold path of :meth:`__contains__` and :meth:`filter`.
        """
        assert not self._has_arbitrary, (
            "_intersect_bounds called on a set containing ==="
        )
        return intersect_specifier_bounds(spec._to_ranges() for spec in self._specs)

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
            :class:`~packaging.version.Version` instance.
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

        :raises TypeError: if ``item`` is not a :class:`str` or
            :class:`~packaging.version.Version`.
        """
        if not isinstance(item, (str, Version)):
            raise TypeError(
                f"SpecifierSet.contains() expected str or Version, "
                f"got {type(item).__name__}"
            )
        version = coerce_version(item)

        if version is not None and installed and version.is_prerelease:
            prereleases = True

        # When item is a string and === is involved, keep it as-is
        # so the comparison isn't done against the normalized form.
        if version is None or (self._has_arbitrary and not isinstance(item, Version)):
            check_item = item
        else:
            check_item = version

        # Fast path: a parseable, local-free version against a rangelike
        # set. The set-level pre-release decision is made first.
        if (
            version is not None
            and not self._has_arbitrary
            and version.local is None
            and self._specs
        ):
            if version.is_prerelease and (
                prereleases is False
                or (prereleases is None and self._prereleases is False)
            ):
                return False

            # Answer per-spec when the intersected bounds aren't already
            # cached. Specs that ``_fast_match`` cannot handle (wildcard,
            # ``~=``, ``<V``/``>V`` family carve-out) fall back to that
            # single spec's bounds via :meth:`Specifier._to_ranges`, so a
            # contains-only workload never pays the ~50 us cost of
            # folding the full set. :meth:`filter` and
            # :meth:`is_unsatisfiable` populate ``_ranges`` when called;
            # once it is, the cheap bounds-only path takes over.
            if (bounds := self._ranges) is None:
                for spec in self._specs:
                    match = spec._fast_match(version)
                    if match is False:
                        return False
                    if match is None and not matches_bounds_only(
                        spec._to_ranges(), version
                    ):
                        return False
                return True

            return matches_bounds_only(bounds, version)

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
            An iterable that can contain version strings and
            :class:`~packaging.version.Version` instances. The items in the
            iterable will be filtered according to the specifier.
        :param prereleases:
            Whether or not to allow prereleases in the returned iterator. If set to
            ``None`` (the default), it will follow the recommendation from :pep:`440`
            and match prereleases if there are no other versions.
        :param key:
            A callable that takes a single argument (an item from the iterable) and
            returns a version string or :class:`~packaging.version.Version`
            instance to be used for filtering.

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

        .. versionchanged:: 26.1

            Added the ``key`` parameter.
        """
        # Resolve the default when no explicit value is given (the
        # ``resolve_prereleases`` rule). ``self.prereleases`` scans every
        # spec, so resolve it once and only when needed.
        if prereleases is None:
            resolved = self.prereleases
            if resolved is not None:
                prereleases = resolved
        # Empty set with ``prereleases=True`` admits everything; skip the
        # range-build and yield the iterable as-is.
        if not self._has_arbitrary and not self._specs and prereleases is True:
            return iter(iterable)
        # Non-empty sets without ``===`` use the bounds-only fast path
        # (see :meth:`Specifier.filter` for the rationale). The empty
        # :class:`SpecifierSet` and ``===`` cases route through
        # :class:`VersionRange`'s public filter so it can admit
        # unparsable strings and arbitrary-equality literals.
        if not self._has_arbitrary and self._specs:
            if (bounds := self._ranges) is None:
                bounds = self._ranges = self._intersect_bounds()

            return filter_by_ranges(
                ranges=bounds,
                iterable=iterable,
                key=key,
                prereleases=prereleases,
            )

        return self.to_range().filter(iterable, key=key, prereleases=prereleases)
