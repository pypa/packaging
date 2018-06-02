Specifiers
==========

.. currentmodule:: packaging.specifiers

A core requirement of dealing with dependencies is the ability to specify what
versions of a dependency you accept. This module implements the :pep:`440`
dependency specification scheme.

Usage
-----

.. doctest::

    >>> from packaging.specifiers import SpecifierSet
    >>> from packaging.version import Version
    >>> spec1 = SpecifierSet("~=1.0")
    >>> spec1
    <SpecifierSet('~=1.0')>
    >>> spec2 = SpecifierSet(">=1.0")
    >>> spec2
    <SpecifierSet('>=1.0')>
    >>> # We can combine specifiers
    >>> combined_spec = spec1 & spec2
    >>> combined_spec
    <SpecifierSet('>=1.0,~=1.0')>
    >>> # We can also implicitly combine a string specifier
    >>> combined_spec &= "!=1.1"
    >>> combined_spec
    <SpecifierSet('!=1.1,>=1.0,~=1.0')>
    >>> # Create a few versions to check for contains.
    >>> v1 = Version("1.0a5")
    >>> v2 = Version("1.0")
    >>> # We can check a version object to see if it falls within a specifier
    >>> v1 in combined_spec
    False
    >>> v2 in combined_spec
    True
    >>> # We can even do the same with a string based version
    >>> "1.4" in combined_spec
    True
    >>> # Finally we can filter a list of versions to get only those which are
    >>> # contained within our specifier.
    >>> list(combined_spec.filter([v1, v2, "1.4"]))
    [<Version('1.0')>, '1.4']


Reference
---------

.. class:: SpecifierSet(specifiers, prereleases=None)

    This class abstracts the handling of project dependency specification . It
    can be passed a single specifier (``>=3.0``), a comma-separated list of
    specifiers (``>=3.0,!=3.1``), or no specifier at all. An attempt is made
    to parse each individual specifier as a :pep:`440` specifier
    (:class:`Specifier`) or, should that fail, as a legacy, setuptools style
    specifier (:class:`LegacySpecifier`).

    The ``&`` operator combines specifier sets (``SpecifierSet(">2") &
    SpecifierSet("<4")``).  Version specifiers in string form are also
    accepted (``SpecifierSet(">2") & "!=3.0, <4"``).  A specifier set
    with a ``True`` :attr:`prereleases` value cannot be combined with
    a specifier set having a ``False`` :attr:`prereleases`.  Attemping
    to do so raises a :exc:`ValueError`.

    The membership test functions accept versions as either raw
    strings or instantiated objects.

    :param str specifiers: A string representation of a version
                           specifier or a string containing a
                           comma-separated list of version specifiers.
                           Parsed and normalized before use.
    :param prereleases: Whether the SpecifierSet should accept prerelease
                        versions. The default (``None``) accepts prerelease
                        versions when the given ``specifiers`` allow such
                        versions.
    :type prereleases: bool or None
    :raises InvalidSpecifier: Raised when any of the given ``specifiers`` are
                              not parseable.

    .. attribute:: prereleases

        A boolean value indicating whether this :class:`SpecifierSet`
        should include pre-release versions. This can be
        set to either ``True`` or ``False`` to explicitly enable or disable
        prereleases or it can be set to ``None`` (the default) to
        autodetect from the specifiers the set contains.

    .. method:: __contains__(version)

        This is the more Pythonic version of :meth:`contains()`, but does not
        allow override of the ``prereleases`` argument.  If you need that,
        use :meth:`contains()`.

        See :meth:`contains()`.

    .. method:: contains(version, prereleases=None)

        Determines if ``version``, which can be either a version string, a
        :class:`Version`, or a :class:`LegacyVersion` object, is contained
        within this set of specifiers.

        ``version`` either matches or does not match prereleases based on the
        ``prereleases`` parameter. When ``prereleases`` is ``None`` (the
        default) the :attr:`prereleases` attributes of the set's specifiers
        determine whether to allow them. Otherwise the boolean value of
        ``prereleases`` to determines whether they are allowed.

    .. method:: __len__()

        Return the number of specifiers in the specifier set.

    .. method:: __iter__()

        Return an iterator over all the underlying :class:`Specifier` (or
        :class:`LegacySpecifier`) instances in the specifier set.

    .. method:: filter(iterable, prereleases=None)

        Takes an iterable containing version strings, :class:`Version`, and
        :class:`LegacyVersion` instances.  Filters the iterable returning
        an iterable containing only items matching the rules of the
        specifier.

        This method is smarter than ``filter(Specifier().contains,
        [...])``. It implements the :pep:`440` rule where a prerelease item
        SHOULD be accepted when no other versions match the given specifier.

        The ``prereleases`` parameter functions similar to the parameter of
        the same name in :meth:`contains`. If the value is ``None`` (the
        default) it intelligently decides whether to allow prereleases based
        on the specifier's interpretation under the rules of :pep:`440`, and
        the specifier's :attr:`prereleases` setting. Otherwise it acts as a
        boolean which enables or disables the inclusion of all prerelease
        versions.
        See :meth:`SpecifierSet.filter()`.


.. class:: Specifier(specifier, prereleases=None)

    This class abstracts the handling of a single :pep:`440` compatible
    specifier. Instantiating this class manually is generally not required,
    it is better to work with :class:`SpecifierSet`.

    Object equality is based solely on the given ``specifier`` text.
    Instances of this class are equal (compare ``==``) when their
    :attr:`operator` and :attr:`version` are equal.

    :param str specifier: The string representation of a version
                          specifier.  Parsed and normalized before
                          use.
    :param prereleases: Whether the specifier should accept prerelease
                        versions. The default (``None``) accepts prerelease
                        versions when the given ``specifier`` allows such
                        versions.
    :type prereleases: bool or None
    :raises InvalidSpecifier: Raised when the ``specifier`` does not fully
                              conform to :pep:`440` and therefore cannot be
                              parsed.

    .. attribute:: operator

        The string value of the comparison operator part of the ``specifier``.
        The value is as given, not normalized, but is stripped of leading and
        trailing whitespace.

    .. attribute:: version

        The string value of the version part of the ``specifier``.  The value
        is as given, not normalized, but is stripped of leading and trailing
        whitespace.

    .. attribute:: prereleases

        See :attr:`SpecifierSet.prereleases`.

    .. method:: __contains__(version)

        See :meth:`SpecifierSet.__contains__()`.

    .. method:: contains(version, prereleases=None)

        See :meth:`SpecifierSet.contains()`.

    .. method:: filter(iterable, prereleases=None)

        See :meth:`SpecifierSet.filter()`.


.. class:: LegacySpecifier(specifier, prereleases=None)

    This class abstracts the handling of a single legacy, setuptools style
    specifier. Instantiating this class manually is generally not required,
    it is better to work with :class:`SpecifierSet`.

    Object equality is based solely on the given ``specifier`` text.
    Instances of this class are equal (compare ``==``) when their
    :attr:`operator` and :attr:`version` are equal.

    :param str specifier: The string representation of a version specifier.
                          Parsed and normalized before use.
    :param prereleases: Whether the specifier should accept prerelease
                        versions. The default (``None``) accepts prerelease
                        versions when the given ``specifier`` allows such
                        versions.
    :type prereleases: bool or None
    :raises InvalidSpecifier: Raised when the ``specifier`` is not parseable.

    .. attribute:: operator

        The string value of the comparison operator part of the ``specifier``.
        The value is as given, not normalized, but is stripped of leading and
        trailing whitespace.

    .. attribute:: version

        The string value of the version part of the ``specifier``.  The value
        is as given, not normalized, but is stripped of leading and trailing
        whitespace.

    .. attribute:: prereleases

        See :attr:`SpecifierSet.prereleases`.

    .. method:: __contains__(version)

        See :meth:`SpecifierSet.__contains__()`.

    .. method:: contains(version, prereleases=None)

        See :meth:`SpecifierSet.contains()`.

    .. method:: filter(iterable, prereleases=None)

        See :meth:`SpecifierSet.filter()`.


.. exception:: InvalidSpecifier

    Raised when a specifier string cannot be parsed.
