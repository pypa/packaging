Specifiers
==========

.. currentmodule:: packaging.specifiers

A core requirement of dealing with dependency is the ability to specify what
versions of a dependency are acceptable for you. `PEP 440`_ defines the
standard specifier scheme which has been implemented by this module.

Usage
-----

.. doctest::

    >>> from packaging.specifiers import Specifier
    >>> from packaging.version import Version
    >>> spec1 = Specifier("~=1.0")
    >>> spec1
    <Specifier('~=1.0')>
    >>> spec2 = Specifier(">=1.0")
    >>> spec2
    <Specifier('>=1.0')>
    >>> # We can combine specifiers
    >>> combined_spec = spec1 & spec2
    >>> combined_spec
    <Specifier('>=1.0,~=1.0')>
    >>> # We can also implicitly combine a string specifier
    >>> combined_spec &= "!=1.1"
    >>> combined_spec
    <Specifier('!=1.1,>=1.0,~=1.0')>
    >>> # Create a few versions to check for contains.
    >>> v1 = Version("1.0a5")
    >>> v2 = Version("1.0")
    >>> # We can check a version object to see if it falls within a specifier
    >>> combined_spec.contains(v1)
    False
    >>> combined_spec.contains(v2)
    True
    >>> # We can even do the same with a string based version
    >>> combined_spec.contains("1.4")
    True
    >>> # Finally we can filter a list of versions to get only those which are
    >>> # contained within our specifier.
    >>> list(combined_spec.filter([v1, v2, "1.4"]))
    [<Version('1.0')>, '1.4']


Reference
---------

.. class:: Specifier(specifier, prereleases=None)

    This class abstracts handling of specifying the dependencies of a project.
    It implements the scheme defined in `PEP 440`_. You may combine Specifier
    instances using the ``&`` operator (``Specifier(">2") & Specifier(">3")``).

    Both the membership test and the combination supports using raw strings
    in place of already instantiated objects.

    :param str specifier: The string representation of a specifier which will
                          be parsed and normalized before use.
    :param bool prereleases: This tells the specifier if it should accept
                             prerelease versions if applicable or not. The
                             default of ``None`` will autodetect it from the
                             given specifiers.
    :raises InvalidSpecifier: If the ``specifier`` does not conform to PEP 440
                              in any way then this exception will be raised.

    .. attribute:: prereleases

        A boolean value indicating whether this :class:`Specifier` represents
        a specifier that includesa pre-release versions. This can be set to
        either ``True`` or ``False`` to explicitly enable or disable
        prereleases or it can be set to ``None`` (the default) to enable
        autodetection.

    .. method:: contains(version, prereleases=None)

        Determines if ``version``, which can be either a version string, a
        :class:`Version`, or a :class:`LegacyVersion` object, is contained
        within this specifier.

        This will either match or not match prereleases based on the
        ``prereleases`` parameter. When ``prereleases`` is set to ``None``
        (the default) it will use the ``Specifier().prereleases`` attribute to
        determine if to allow them. Otherwise it will use the boolean value of
        the passed in value to determine if to allow them or not.

    .. method:: filter(iterable, prereleases=None)

        Takes an iterable that can contain version strings, :class:`Version`,
        and :class:`LegacyVersion` instances and will then filter it, returning
        an iterable that contains only items which match the rules of this
        specifier object.

        This method is smarter than just
        ``filter(Specifier().contains, [...])`` because it implements the rule
        from PEP 440 where a prerelease item SHOULD be accepted if no other
        versions match the given specifier.

        The ``prereleases`` parameter functions similarly to that of the same
        parameter in ``contains``. If the value is ``None`` (the default) then
        it will intelligently decide if to allow prereleases based on the
        specifier, the ``Specifier().prereleases`` value, and the PEP 440
        rules. Otherwise it will act as a boolean which will enable or disable
        all prerelease versions from being included.


.. exception:: InvalidSpecifier

    Raised when attempting to create a :class:`Specifier` with a specifier
    string that does not conform to `PEP 440`_.


.. _`PEP 440`: https://www.python.org/dev/peps/pep-0440/
