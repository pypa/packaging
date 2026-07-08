Version Ranges
==============

.. currentmodule:: packaging.ranges

A :class:`VersionRange` is the set of :class:`~packaging.version.Version`
values accepted by a :class:`~packaging.specifiers.SpecifierSet`, viewed as
intervals on the PEP 440 ordering. It supports intersection, union,
complement, and difference, so tooling that combines many requirements, such
as a resolver, can work on the intervals directly.

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
    >>> # The union covers either side, leaving any gap between them
    >>> u = SpecifierSet("<1.0").to_range() | SpecifierSet(">=2.0").to_range()
    >>> Version("0.5") in u
    True
    >>> Version("1.5") in u
    False
    >>> # The complement is every other version
    >>> Version("0.5") in ~r
    True
    >>> # Filter an iterable of versions
    >>> list(r.filter(["0.9", "1.5", "2.0"]))
    ['1.5']
    >>> # An unsatisfiable set produces the empty range
    >>> SpecifierSet(">=2.0,<1.0").to_range().is_empty
    True

Pre-releases
------------

A specifier that names a pre-release, such as ``>=2.0b1``, opts in pre-releases
only for the versions it asks for. That opt-in region is carried as ranges are
combined, so a union with a plain range keeps the pre-releases it named without
admitting every pre-release below them:

.. doctest::

    >>> a = SpecifierSet(">=1.0").to_range()
    >>> b = SpecifierSet(">=2.0b1").to_range()
    >>> list((a | b).filter(["1.5b1", "2.0b1", "2.5"]))
    ['2.0b1', '2.5']

``2.0b1`` is admitted because ``>=2.0b1`` asked for it; ``1.5b1`` is not, since
the opt-in never came from ``>=1.0``.

The opt-in is also clipped to the range's own bounds, so combining ranges never
force-admits a pre-release outside every operand's request. ``>=2.0b1,<3`` opts
pre-releases in only below ``3``, so unioning it with an unrelated higher range
does not admit a pre-release up in that range:

.. doctest::

    >>> capped = SpecifierSet(">=2.0b1,<3").to_range()
    >>> other = SpecifierSet(">=3.5,<4").to_range()
    >>> list((capped | other).filter(["3.6b1", "3.7"]))
    ['3.7']

Neither operand admits ``3.6b1``: ``>=3.5,<4`` names no pre-release and
``>=2.0b1,<3`` opts in only below ``3``.

Set difference
--------------

``a - b`` is set difference: the versions in ``a`` but not ``b``. It agrees with
``a & ~b`` on the version set and the opt-in region, so subtracting a
pre-release-naming range does not leak its pre-releases into the result:

.. doctest::

    >>> base = SpecifierSet(">=1.0").to_range()
    >>> excluded = SpecifierSet(">=2.0b1").to_range()
    >>> list((base - excluded).filter(["1.9", "2.0a1"]))
    ['1.9']
    >>> (base - excluded) == (base & ~excluded)
    True

Comparing ranges
----------------

Equality on a :class:`VersionRange` is structural: it compares the bounds, the
``===`` admit/reject literals, the arbitrary-string flag, the configured
pre-release policy, and the opt-in region, not only the version set. Equal
ranges therefore behave identically under :meth:`VersionRange.contains` and
:meth:`VersionRange.filter`.

For set relations use :meth:`VersionRange.is_subset`,
:meth:`VersionRange.is_superset`, and :meth:`VersionRange.is_disjoint` rather
than comparing intersections by hand. Intersection can change the opt-in
region without changing the version set, so the textbook subset test
``a & b == a`` can report a false negative. Each method compares the version
sets directly, so it is not affected by that opt-in difference:

.. doctest::

    >>> from packaging.specifiers import SpecifierSet
    >>> a = SpecifierSet(">=1.0").to_range()
    >>> b = SpecifierSet(">=1.0a1").to_range()
    >>> # Every version >=1.0 is also >=1.0a1, so a is a subset of b. But b
    >>> # opts pre-releases in, so ``a & b`` and ``a`` differ in the opt-in region:
    >>> a & b == a
    False
    >>> a.is_subset(b)
    True
    >>> b.is_superset(a)
    True
    >>> a.is_disjoint(b)
    False
    >>> # The opt-in difference is observable: a & b force-admits pre-releases
    >>> # in b's region that plain a filters out
    >>> list(a.filter(["2.0a1", "2.5"]))
    ['2.5']
    >>> list((a & b).filter(["2.0a1", "2.5"]))
    ['2.0a1', '2.5']

Like :meth:`VersionRange.intersection`, :meth:`VersionRange.union`, and
:meth:`VersionRange.difference`, these predicates require both operands to share
the same configured pre-release policy and raise :exc:`ValueError` otherwise.

Different specifiers that denote the same range, opt-in region included,
canonicalize to one form, so they compare equal. ``>1.0a1`` excludes
``1.0a1``'s post-releases per PEP 440, so its smallest member is ``1.0a2.dev0``,
exactly the set of ``>=1.0a2.dev0``:

.. doctest::

    >>> r1 = SpecifierSet(">1.0a1").to_range()
    >>> r2 = SpecifierSet(">=1.0a2.dev0").to_range()
    >>> r1 == r2
    True
    >>> third = SpecifierSet("<2.0").to_range()
    >>> (r1 & third) == (r2 & third)
    True

The opt-in region is also part of equality. ``<1.0.post0.dev0`` and
``<=1.0`` cover the same versions, but the first autodetects an opt-in
region from its ``.dev`` bound, so it admits pre-releases by default,
while the second does not; they are not substitutable and compare unequal:

.. doctest::

    >>> SpecifierSet("<1.0.post0.dev0").to_range() == SpecifierSet("<=1.0").to_range()
    False

Limits of the model
-------------------

The pre-release opt-in is not itself a set. PEP 440 opts a whole specifier set
in when any one specifier names a pre-release, so ``&`` is requirement
conjunction (a comma-merge of the two specifier sets), not plain intersection,
on the opt-in. No model can keep that parity with
:class:`~packaging.specifiers.SpecifierSet`, exclusion soundness (an exclusion
grants no opt-in), and an involutive complement at the same time. This model
keeps parity and soundness, so complement drops the opt-in and a few Boolean
identities do not hold once an operand carries one.

A double complement therefore erases the opt-in rather than restoring it. ``~~r``
keeps ``r``'s versions but not its eager pre-releases:

.. doctest::

    >>> b = SpecifierSet(">=2.0b1").to_range()
    >>> list(b.filter(["2.0b1", "2.5"]))
    ['2.0b1', '2.5']
    >>> list((~~b).filter(["2.0b1", "2.5"]))
    ['2.5']
    >>> ~~b == b
    False

The erasure is still well behaved: ``~~~r == ~r``, both De Morgan laws hold, and
``r & ~r`` is empty.

.. doctest::

    >>> ~~~b == ~b
    True
    >>> (b & ~b).is_empty
    True

Because complement drops the opt-in while union keeps it, ``b | full()`` carries
``b``'s opt-in, which the full range (with no eager pre-release) does not, so it
does not collapse to :meth:`VersionRange.full`. For the same reason union no
longer distributes over intersection, and the absorption laws do not hold, when
an operand carries an opt-in:

.. doctest::

    >>> a = SpecifierSet(">=1.0").to_range()
    >>> b | VersionRange.full() == VersionRange.full()
    False
    >>> a & (a | b) == a
    False

Intersection still distributes over union, ``a - b`` agrees with ``a & ~b`` on
the version set and the opt-in region, and every law holds on the version set
as usual. The opt-in region makes the identities above differ only when a
specifier named a pre-release.

The arbitrary-string flag has corners of its own. ``SpecifierSet("")`` matches
even strings that are not PEP 440 versions, so its range,
:meth:`VersionRange.full`, admits them too; pass ``admit_arbitrary=False`` for
the versions-only full range. Only those ranges and ``===`` literals admit
such strings: combining ranges never grants an admission the operands did not
have, so ``~r`` stays version-only for any version-only ``r``. The flag rides
along where that is harmless, keeping ``~~full() == full()`` and union
idempotent, but an intersection or difference that empties out does not
remember it:

.. doctest::

    >>> f = VersionRange.full()
    >>> "wat" in f
    True
    >>> "wat" in VersionRange.full(admit_arbitrary=False)
    False
    >>> ~~f == f
    True
    >>> (~f | ~f) == ~f
    True
    >>> (f & ~f) == VersionRange.empty()
    True
    >>> (f & ~f) == ~f
    False

Reference
---------

.. automodule:: packaging.ranges
    :members:
    :special-members:
