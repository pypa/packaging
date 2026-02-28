Dependency Groups
=================

.. currentmodule:: packaging.dependency_groups

Package data as defined in ``pyproject.toml`` may include lists of dependencies
in named groups. This is described by the
:ref:`dependency groups specification <pypug:dependency-groups>`, which defines
the ``[dependency-groups]`` table.

This module provides tools for resolving group names to lists of requirements,
most notably expanding ``include-group`` directives.

Usage
-----

Two primary interfaces are offered. An object-based one which caches results and
provides ``Requirements`` as its results:

.. doctest::

    >>> from packaging.dependency_groups import DependencyGroupResolver
    >>> coverage = ["coverage"]
    >>> test = ["pytest", {"include-group": "coverage"}]
    >>> # A resolver is defined on a mapping of group names to group data, as
    >>> # you might get by loading the [dependency-groups] TOML table.
    >>> resolver = DependencyGroupResolver({"test": test, "coverage": coverage})
    >>> # resolvers support expanding group names to Requirements
    >>> resolver.resolve("coverage")
    (<Requirement('coverage')>,)
    >>> resolver.resolve("test")
    (<Requirement('pytest')>, <Requirement('coverage')>)
    >>> # resolvers can also be used to lookup the dependency groups without
    >>> # expanding includes
    >>> resolver.lookup("test")
    (<Requirement('pytest')>, DependencyGroupInclude('coverage'))

And a simpler functional interface which responds with strings:

.. doctest::

    >>> from packaging.dependency_groups import resolve_dependency_groups
    >>> coverage = ["coverage"]
    >>> test = ["pytest", {"include-group": "coverage"}]
    >>> groups = {"test": test, "coverage": coverage}
    >>> resolve_dependency_groups(groups, "test")
    ('pytest', 'coverage')

Reference
---------

Functional Interface
''''''''''''''''''''

.. autofunction:: resolve_dependency_groups


Object Model Interface
''''''''''''''''''''''

.. autoclass:: DependencyGroupInclude
    :members:

.. autoclass:: DependencyGroupResolver
    :members:

Exceptions
''''''''''

.. autoclass:: DuplicateGroupNames
    :members:

.. autoclass:: CyclicDependencyGroup
    :members:

.. autoclass:: InvalidDependencyGroupObject
    :members:
