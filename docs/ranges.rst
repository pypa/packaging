Version Ranges
==============

.. currentmodule:: packaging.ranges

A :class:`VersionRange` is the set of :class:`~packaging.version.Version`
values accepted by a :class:`~packaging.specifiers.SpecifierSet`, viewed as
intervals on the PEP 440 ordering. It supports intersection, union, and
complement, so tooling that combines many requirements, such as a resolver,
can work on the intervals directly.

Usage
-----

.. doctest::

    >>> from packaging.ranges import VersionRange
    >>> from packaging.specifiers import SpecifierSet
    >>> from packaging.version import Version
    >>> # Build a range from a specifier set
    >>> r = SpecifierSet(">=1.0,<2.0").to_range()
    >>> r
    <VersionRange '[1.0, 2.0.dev0)'>
    >>> Version("1.5") in r
    True
    >>> Version("2.0") in r
    False
    >>> # Combine ranges with set algebra
    >>> a = SpecifierSet(">=1.0").to_range()
    >>> b = SpecifierSet("<2.0").to_range()
    >>> a & b == r
    True
    >>> # The complement is every other version
    >>> Version("0.5") in ~r
    True
    >>> # Filter an iterable of versions
    >>> list(r.filter(["0.9", "1.5", "2.0"]))
    ['1.5']
    >>> # An unsatisfiable set produces the empty range
    >>> SpecifierSet(">=2.0,<1.0").to_range().is_empty
    True

Comparing ranges
----------------

Equality on a :class:`VersionRange` is structural: two ranges are equal only
when they behave the same under :meth:`VersionRange.contains` and
:meth:`VersionRange.filter`. Equality covers the pre-release policy and any
``===`` admission, not only the versions matched. Intersection can change one
of those without changing the version set, so the textbook subset test
``a & b == a`` can report a false negative. Use the algebra and
:attr:`VersionRange.is_empty` for set relations:

.. doctest::

    >>> from packaging.specifiers import SpecifierSet
    >>> a = SpecifierSet(">=1.0").to_range()
    >>> b = SpecifierSet(">=1.0a1").to_range()
    >>> # a is a subset of b (every version >=1.0 is also >=1.0a1), but b
    >>> # admits pre-releases, so ``a & b`` and ``a`` differ only in policy:
    >>> a & b == a
    False
    >>> (a & ~b).is_empty       # subset: a has no version outside b
    True
    >>> (a & b).is_empty        # disjoint: a and b share no version
    False

Different specifiers for the same set of versions canonicalize to one form, so
they compare equal. ``>1.0a1`` excludes ``1.0a1``'s post-releases per PEP 440,
so its smallest member is ``1.0a2.dev0``, exactly the set of ``>=1.0a2.dev0``:

.. doctest::

    >>> SpecifierSet(">1.0a1").to_range() == SpecifierSet(">=1.0a2.dev0").to_range()
    True

The pre-release policy is still part of equality. ``<1.0.post0.dev0`` and
``<=1.0`` cover the same versions, but the first admits pre-releases by default
(its bound is a ``.dev`` release) while the second does not, so they are not
substitutable and compare unequal:

.. doctest::

    >>> SpecifierSet("<1.0.post0.dev0").to_range() == SpecifierSet("<=1.0").to_range()
    False

Reference
---------

.. automodule:: packaging.ranges
    :members:
    :special-members:
