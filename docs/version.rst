Version Handling
================

.. currentmodule:: packaging.version

A core requirement of dealing with packages is the ability to work with
versions. `PEP 440`_ defines the standard version scheme for Python packages
which has been implemented by this module.

Usage
-----

.. doctest::

    >>> from packaging.version import Version, Specifier
    >>> v1 = Version("1.0a5")
    >>> v2 = Version("1.0")
    >>> v1
    <Version('1.0a5')>
    >>> v2
    <Version('1.0')>
    >>> v1 < v2
    True
    >>> v1.is_prerelease
    True
    >>> v2.is_prerelease
    False
    >>> Version("french toast")
    Traceback (most recent call last):
        ...
    InvalidVersion: Invalid version: 'french toast'
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
    >>> # We can check a version object to see if it falls within a specifier
    >>> v1 in combined_spec
    False
    >>> v2 in combined_spec
    True
    >>> # We can even do the same with a string based version
    >>> "1.4" in combined_spec
    True


Reference
---------

.. class:: Version(version)

    This class abstracts handling of a project's versions. It implements the
    scheme defined in `PEP 440`_. A :class:`Version` instance is comparison
    aware and can be compared and sorted using the standard Python interfaces.

    :param str version: The string representation of a version which will be
                        parsed and normalized before use.
    :raises InvalidVersion: If the ``version`` does not conform to PEP 440 in
                            any way then this exception will be raised.

    .. attribute:: public

        A string representing the public version portion of this ``Version()``.

    .. attribute:: local

        A string representing the local version portion of this ``Version()``
        if it has one, or ``None`` otherwise.

    .. attribute:: is_prerelease

        A boolean value indicating whether this :class:`Version` instance
        represents a prerelease or a final release.


.. class:: LegacyVersion(version)

    This class abstracts handling of a project's versions if they are not
    compatible with the scheme defined in `PEP 440`_. It implements a similar
    interface to that of :class:`Version` however it is considered unorderable
    and many of the comparison types are not implemented.

    :param str version: The string representation of a version which will be
                        used as is.

    .. attribute:: public

        A string representing the public version portion of this
        :class:`LegacyVersion`. This will always be the entire version string.

    .. attribute:: local

        This will always be ``None`` since without `PEP 440`_ we do not have
        the concept of a local version. It exists primarily to allow a
        :class:`LegacyVersion` to be used as a stand in for a :class:`Version`.

    .. attribute:: is_prerelease

        A boolean value indicating whether this :class:`LegacyVersion`
        represents a prerelease or a final release. Since without `PEP 440`_
        there is no concept of pre or final releases this will always be
        `False` and exists for compatibility with :class:`Version`.


.. class:: Specifier(specifier)

    This class abstracts handling of specifying the dependencies of a project.
    It implements the scheme defined in `PEP 440`_. You can test membership
    of a particular version within a set of specifiers in a :class:`Specifier`
    instance by using the standard ``in`` operator (e.g.
    ``Version("2.0") in Specifier("==2.0")``). You may also combine Specifier
    instances using the ``&`` operator (``Specifier(">2") & Specifier(">3")``).

    Both the membership test and the combination supports using raw strings
    in place of already instantiated objects.

    :param str specifier: The string representation of a specifier which will
                          be parsed and normalized before use.
    :raises InvalidSpecifier: If the ``specifier`` does not conform to PEP 440
                              in any way then this exception will be raised.


.. class:: InvalidVersion

    Raised when attempting to create a :class:`Version` with a version string
    that does not conform to `PEP 440`_.


.. class:: InvalidSpecifier

    Raised when attempting to create a :class:`Specifier` with a specifier
    string that does not conform to `PEP 440`_.


.. _`PEP 440`: https://www.python.org/dev/peps/pep-0440/
