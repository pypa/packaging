Ranges
======

.. versionadded:: 26.3

.. currentmodule:: packaging.ranges

A :class:`~packaging.ranges.VersionRange` represents the set of
:class:`~packaging.version.Version` values matched by a
:class:`~packaging.specifiers.Specifier` or
:class:`~packaging.specifiers.SpecifierSet`. Unlike a
:class:`~packaging.specifiers.SpecifierSet`, ranges are closed under
intersection, union, and complement, so questions like "do these two
constraints overlap?" or "is this constraint a subset of that one?"
reduce to direct set operations.

Constructing a range
--------------------

Build a range from a :class:`~packaging.specifiers.Specifier` or
:class:`~packaging.specifiers.SpecifierSet` using
:meth:`~packaging.specifiers.Specifier.to_range` or
:meth:`~packaging.specifiers.SpecifierSet.to_range`:

.. doctest::

    >>> from packaging.ranges import VersionRange
    >>> from packaging.specifiers import Specifier, SpecifierSet
    >>> r = SpecifierSet(">=1.0,<2.0").to_range()
    >>> "1.5" in r
    True
    >>> "2.0" in r
    False

The classmethods :meth:`VersionRange.from_specifier` and
:meth:`VersionRange.from_specifier_set` produce the same results and
are useful when only a :class:`VersionRange` reference is in scope.

Three factories return common identity ranges:

.. doctest::

    >>> VersionRange.empty().is_empty
    True
    >>> "1.5" in VersionRange.full()
    True
    >>> "1.0" in VersionRange.singleton("1.0")
    True

Each accepts a keyword-only ``prereleases=True``/``False`` to stamp the
configured pre-release policy so the result combines cleanly with ranges
built from a :class:`~packaging.specifiers.SpecifierSet` carrying the
same policy.

Calling ``VersionRange()`` directly raises :exc:`TypeError`; use one
of the factories above.

Set algebra
-----------

:class:`VersionRange` supports intersection, union, and complement
via the :meth:`~VersionRange.intersection`,
:meth:`~VersionRange.union`, and :meth:`~VersionRange.complement`
methods, or the ``&``, ``|``, and ``~`` operator aliases. Every
operation returns a new range; operands are not mutated.

.. doctest::

    >>> ge1 = SpecifierSet(">=1.0").to_range()
    >>> lt2 = SpecifierSet("<2.0").to_range()
    >>> "1.5" in (ge1 & lt2)
    True
    >>> "2.5" in (ge1 | lt2)
    True
    >>> # Double-complement is the original range.
    >>> ~~ge1 == ge1
    True
    >>> # A range and its complement are disjoint.
    >>> bool(ge1 & ~ge1)
    False

:meth:`~VersionRange.complement` is one-way for ``===`` literals that
do not parse as PEP 440 versions: the literal drops out of the first
complement, so ``~~(===wat)`` is empty. See the :class:`VersionRange`
class reference for details.

Set operations answer overlap and subset questions directly:

.. doctest::

    >>> a = SpecifierSet(">=1.0,<2.0").to_range()
    >>> b = SpecifierSet(">=1.5,<3.0").to_range()
    >>> # Do these constraints overlap?
    >>> bool(a & b)
    True
    >>> # Is *a* entirely contained in *b*?
    >>> (a & b) == a
    False
    >>> narrow = SpecifierSet(">=1.0,<1.5").to_range()
    >>> wide = SpecifierSet(">=1.0,<2.0").to_range()
    >>> (narrow & wide) == narrow
    True

Intersection and union require both operands to share the same
configured pre-release policy (``None``, ``True``, or ``False``); a
mismatch raises :exc:`ValueError`. The shared policy carries onto the
result. Complement preserves the policy of its single operand.

Membership and filtering
------------------------

:meth:`~VersionRange.filter` mirrors
:meth:`~packaging.specifiers.SpecifierSet.filter`, including the PEP 440
pre-release behaviour: with ``prereleases=None`` (the default),
pre-releases are buffered and emitted only when the iterable contains no
in-range final release.

.. doctest::

    >>> from packaging.version import Version
    >>> r = SpecifierSet(">=1.0,<2.0").to_range()
    >>> "1.5" in r
    True
    >>> Version("1.5") in r
    True
    >>> list(r.filter(["0.9", "1.5", "2.0"]))
    ['1.5']

Membership (``in``) mirrors
:meth:`~packaging.specifiers.SpecifierSet.__contains__`: a configured
``prereleases=False`` excludes pre-releases from both ``in`` and
:meth:`~VersionRange.filter`. Autodetect alone does not exclude them
(PEP 440's "match pre-releases when there are no other versions" default
still applies).

.. doctest::

    >>> excludes_pre = SpecifierSet(">=1.0", prereleases=False).to_range()
    >>> "2.0a1" in excludes_pre
    False
    >>> list(excludes_pre.filter(["1.5", "2.0a1"]))
    ['1.5']

Equality and hashing compare the configured pre-release policy along
with the bounds and any ``===`` literals: two ranges built with
different ``prereleases=`` values are not equal, because the explicit-
False policy rejects items under ``in`` that the autodetect policy
admits.

.. doctest::

    >>> r_default = SpecifierSet(">=1.0,<2.0").to_range()
    >>> r_no_pre = SpecifierSet(">=1.0,<2.0", prereleases=False).to_range()
    >>> r_default == r_no_pre
    False
    >>> "1.5a1" in r_default
    True
    >>> "1.5a1" in r_no_pre
    False

:class:`VersionRange` accepts ``===L`` arbitrary-equality literals
from a :class:`~packaging.specifiers.Specifier` or
:class:`~packaging.specifiers.SpecifierSet`. Set algebra over literals
is best effort, and structural equality may differ from
:class:`~packaging.specifiers.SpecifierSet` (literals are case-folded).
Prefer the standard comparison operators where possible.

Converting back to a SpecifierSet
---------------------------------

:meth:`~VersionRange.to_specifier_set` returns a single
:class:`~packaging.specifiers.SpecifierSet` that matches the same
versions as the range, or ``None`` when no such single set exists.
Redundant specifiers are dropped along the way, so the round trip
doubles as a normalisation step:

.. doctest::

    >>> r = SpecifierSet(">=1.0,<2.0,!=1.5").to_range()
    >>> str(r.to_specifier_set())
    '!=1.5,<2.0,>=1.0'
    >>> # ``>2`` is subsumed by ``>=3``; ``!=1.0`` is outside ``>=3``.
    >>> str(SpecifierSet("!=1.0,>2,>=3").to_range().to_specifier_set())
    '>=3'

PEP 440 specifier sets are not closed under union, so the disjoint
union of two intervals returns ``None``;
:meth:`~VersionRange.to_specifier_sets` returns one
:class:`~packaging.specifiers.SpecifierSet` per interval:

.. doctest::

    >>> r = (
    ...     SpecifierSet(">=1.0,<2.0").to_range()
    ...     | SpecifierSet(">=3.0,<4.0").to_range()
    ... )
    >>> r.to_specifier_set() is None
    True
    >>> [str(s) for s in r.to_specifier_sets()]
    ['<2.0,>=1.0', '<4.0,>=3.0']

See the :meth:`~VersionRange.to_specifier_set` and
:meth:`~VersionRange.to_specifier_sets` reference below for the precise
round-trip contract and the handling of the empty and full ranges.

Reference
---------

.. autoclass:: packaging.ranges.VersionRange
    :members:
    :special-members: __contains__, __bool__, __eq__, __hash__, __repr__, __and__, __or__, __invert__
    :exclude-members: __new__
