.. SPDX-FileCopyrightText: 2014-2022 Donald Stufft and individual contributors. All rights reserved.
..
.. SPDX-License-Identifier: BSD-2-Clause OR Apache-2.0

Requirements
============

.. currentmodule:: packaging.requirements

Parse a given requirements line for specifying dependencies of a Python
project, using `PEP 508`_ which defines the scheme that has been implemented
by this module.

Usage
-----

.. doctest::

    >>> from packaging.requirements import Requirement
    >>> simple_req = Requirement("name")
    >>> simple_req
    <Requirement('name')>
    >>> simple_req.name
    'name'
    >>> simple_req.url is None
    True
    >>> simple_req.extras
    set()
    >>> simple_req.specifier
    <SpecifierSet('')>
    >>> simple_req.marker is None
    True
    >>> # Requirements can be specified with extras, specifiers and markers
    >>> req = Requirement('name[foo]>=2,<3; python_version>"2.0"')
    >>> req.name
    'name'
    >>> req.extras
    {'foo'}
    >>> req.specifier
    <SpecifierSet('<3,>=2')>
    >>> req.marker
    <Marker('python_version > "2.0"')>
    >>> # Requirements can also be specified with a URL, but may not specify
    >>> # a version.
    >>> url_req = Requirement('name @ https://github.com/pypa ;os_name=="a"')
    >>> url_req.name
    'name'
    >>> url_req.url
    'https://github.com/pypa'
    >>> url_req.extras
    set()
    >>> url_req.marker
    <Marker('os_name == "a"')>
    >>> # You can do simple comparisons between requirement objects:
    >>> Requirement("packaging") == Requirement("packaging")
    True
    >>> # You can also perform simple comparisons between sets of requirements:
    >>> requirements1 = {Requirement("packaging"), Requirement("pip")}
    >>> requirements2 = {Requirement("pip"), Requirement("packaging")}
    >>> requirements1 == requirements2
    True


Reference
---------

.. class:: Requirement(requirement)

    This class abstracts handling the details of a requirement for a project.
    Each requirement will be parsed according to PEP 508.

    :param str requirement: The string representation of a requirement.
    :raises InvalidRequirement: If the given ``requirement`` is not parseable,
                                then this exception will be raised.

    .. attribute:: name

       The name of the requirement.

    .. attribute:: url

      The URL, if any where to download the requirement from. Can be None.

    .. attribute:: extras

      A set of extras that the requirement specifies.

    .. attribute:: specifier

      A :class:`~.SpecifierSet` of the version specified by the requirement.

    .. attribute:: marker

      A :class:`~.Marker` of the marker for the requirement. Can be None.

.. exception:: InvalidRequirement

    Raised when attempting to create a :class:`Requirement` with a string that
    does not conform to PEP 508.

.. _`PEP 508`: https://www.python.org/dev/peps/pep-0508/
