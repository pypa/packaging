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
:meth:`~packaging.specifiers.Specifier.to_range`:

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
    >>> # A range and its complement are always disjoint.
    >>> bool(ge1 & ~ge1)
    False

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

Membership and filtering
------------------------

``in`` and :meth:`~VersionRange.filter` mirror
:class:`~packaging.specifiers.SpecifierSet`'s
:meth:`~packaging.specifiers.SpecifierSet.__contains__` and
:meth:`~packaging.specifiers.SpecifierSet.filter`,
including the PEP 440 pre-release behaviour: with
``prereleases=None`` (the default), pre-releases are buffered and
emitted only when the iterable contains no in-range final release.

.. doctest::

    >>> from packaging.version import Version
    >>> r = SpecifierSet(">=1.0,<2.0").to_range()
    >>> "1.5" in r
    True
    >>> Version("1.5") in r
    True
    >>> list(r.filter(["0.9", "1.5", "2.0"]))
    ['1.5']

Converting back to a SpecifierSet
---------------------------------

:meth:`~VersionRange.to_specifier_set` returns a single
:class:`~packaging.specifiers.SpecifierSet` whose
:meth:`~packaging.specifiers.SpecifierSet.to_range` yields the
same range, or ``None`` if no such single set exists. Redundant
specifiers are dropped, which makes the round-trip a useful
normalisation step:

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

The empty range round-trips through ``SpecifierSet("<0")`` (``<0``
excludes the smallest possible PEP 440 version, ``0.dev0``):

.. doctest::

    >>> VersionRange.empty().to_specifier_set() == SpecifierSet("<0")
    True

Reference
---------

.. autoclass:: packaging.ranges.VersionRange
    :members:
    :special-members: __contains__, __bool__, __eq__, __hash__, __repr__
