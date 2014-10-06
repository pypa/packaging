Version Handling
================

.. currentmodule:: packaging.version

A core requirement of dealing with packages is the ability to work with
versions. `PEP 440`_ defines the standard version scheme for Python packages
which has been implemented by this module.

Usage
-----

.. doctest::

    >>> from packaging.version import Version, parse
    >>> v1 = parse("1.0a5")
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


Reference
---------

.. function:: parse(version)

    This function takes a version string and will parse it as a
    :class:`Version` if the version is a valid PEP 440 version, otherwise it
    will parse it as a :class:`LegacyVersion`.


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
    interface to that of :class:`Version`.

    This class implements the previous de facto sorting algorithm used by
    setuptools, however it will always sort as less than a :class:`Version`
    instance.

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


.. exception:: InvalidVersion

    Raised when attempting to create a :class:`Version` with a version string
    that does not conform to `PEP 440`_.


.. _`PEP 440`: https://www.python.org/dev/peps/pep-0440/
