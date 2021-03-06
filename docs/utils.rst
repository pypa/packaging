Utilities
=========

.. currentmodule:: packaging.utils


A set of small, helper utilities for dealing with Python packages.


Reference
---------

.. function:: canonicalize_name(name)

    This function takes a valid Python package name, and returns the normalized
    form of it.

    :param str name: The name to normalize.

    .. doctest::

        >>> from packaging.utils import canonicalize_name
        >>> canonicalize_name("Django")
        'django'
        >>> canonicalize_name("oslo.concurrency")
        'oslo-concurrency'
        >>> canonicalize_name("requests")
        'requests'

.. function:: canonicalize_version(version)

    This function takes a string representing a package version (or a
    :class:`~packaging.version.Version` instance), and returns the
    normalized form of it.

    :param str version: The version to normalize.

    .. doctest::

        >>> from packaging.utils import canonicalize_version
        >>> canonicalize_version('1.4.0.0.0')
        '1.4'

.. function:: create_wheel_filename(name, version, build, tags)

    Combines a project name, version, build tag, and tag set
    to make a properly formatted wheel filename.

    The project name is normalized such that the non-alphanumeric
    characters are replaced with ``_``. The version is an instance of
    :class:`~packaging.version.Version`. The build tag can be None,
    an empty tuple or a two-item tuple of an integer and a string.
    The tags is set of tags that will be compressed into a wheel
    tag string.

    :param str name: The project name
    :param ~packaging.version.Version version: The project version
    :param Optional[(),(int,str)] build: An optional two-item tuple of an integer and string
    :param set[~packaging.tags.Tag] tags: The set of tags that apply to the wheel

    .. doctest::

        >>> from packaging.utils import create_wheel_filename
        >>> from packaging.tags import Tag
        >>> from packaging.version import Version
        >>> version = Version("1.0")
        >>> tags = {Tag("py3", "none", "any")}
        >>> "foo_bar-1.0-py3-none-any.whl" == create_wheel_filename("foo-bar", version, None, tags)
        True

.. function:: parse_wheel_filename(filename)

    This function takes the filename of a wheel file, and parses it,
    returning a tuple of name, version, build number, and tags.

    The name part of the tuple is normalized. The version portion is an
    instance of :class:`~packaging.version.Version`. The build number
    is ``()`` if there is no build number in the wheel filename,
    otherwise a two-item tuple of an integer for the leading digits and
    a string for the rest of the build number. The tags portion is an
    instance of :class:`~packaging.tags.Tag`.

    :param str filename: The name of the wheel file.

    .. doctest::

        >>> from packaging.utils import parse_wheel_filename
        >>> from packaging.tags import Tag
        >>> from packaging.version import Version
        >>> name, ver, build, tags = parse_wheel_filename("foo-1.0-py3-none-any.whl")
        >>> name
        'foo'
        >>> ver == Version('1.0')
        True
        >>> tags == {Tag("py3", "none", "any")}
        True
        >>> not build
        True

.. function:: create_sdist_filename(name, version)

    Combines the project name and a version to make a valid sdist filename.

    :param str name: The project name
    :param ~packaging.version.Version version: The project version

    .. doctest::

        >>> from packaging.utils import create_sdist_filename
        >>> from packaging.version import Version
        >>> "foo_bar-1.0.tar.gz" == create_sdist_filename("foo-bar", Version("1.0"))
        True

.. function:: parse_sdist_filename(filename)

    This function takes the filename of a sdist file (as specified
    in the `Source distribution format`_ documentation), and parses
    it, returning a tuple of the normalized name and version as
    represented by an instance of :class:`~packaging.version.Version`.

    :param str filename: The name of the sdist file.

    .. doctest::

        >>> from packaging.utils import parse_sdist_filename
        >>> from packaging.version import Version
        >>> name, ver = parse_sdist_filename("foo-1.0.tar.gz")
        >>> name
        'foo'
        >>> ver == Version('1.0')
        True

.. _Source distribution format: https://packaging.python.org/specifications/source-distribution-format/#source-distribution-file-name
