Version Handling
================

.. currentmodule:: packaging.version

A core requirement of dealing with packages is the ability to work with
versions. `PEP 440`_ defines the standard version scheme for Python packages
which has been implemented by this module.

Usage
-----

.. doctest::

    >>> from packaging.version import Version
    >>> v1 = Version("1.0a5")
    >>> v2 = Version("1.0")
    >>> v1
    <Version('1a5')>
    >>> v2
    <Version('1')>
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


.. class:: InvalidVersion:

    Raised when attempting to create a :class:`Version` with a version string
    that does not conform to `PEP 440`_.


.. _`PEP 440`: https://www.python.org/dev/peps/pep-0440/
