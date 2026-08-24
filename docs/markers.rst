Markers
=======

.. currentmodule:: packaging.markers

One extra requirement of dealing with dependencies is the ability to specify
if it is required depending on the operating system or Python version in use.
The :ref:`specification of dependency specifiers <pypug:dependency-specifiers>`
defines the scheme which has been implemented by this module.

Usage
-----

.. doctest::

    >>> from packaging.markers import Marker, UndefinedEnvironmentName
    >>> marker = Marker("python_version>'2'")
    >>> marker
    <Marker('python_version > "2"')>
    >>> # We can evaluate the marker to see if it is satisfied
    >>> marker.evaluate()
    True
    >>> # We can also override the environment
    >>> env = {'python_version': '1.5'}
    >>> marker.evaluate(environment=env)
    False
    >>> # Check whether a marker applies to any of several candidate extras
    >>> Marker('extra == "docs"').evaluate(extras={'docs', 'tests'})
    True
    >>> # Multiple markers can be ANDed
    >>> and_marker = Marker("os_name=='a' and os_name=='b'")
    >>> and_marker
    <Marker('os_name == "a" and os_name == "b"')>
    >>> # Multiple markers can be ORed
    >>> or_marker = Marker("os_name=='a' or os_name=='b'")
    >>> or_marker
    <Marker('os_name == "a" or os_name == "b"')>
    >>> # Markers can be also used with extras, to pull in dependencies if
    >>> # a certain extra is being installed
    >>> extra = Marker('extra == "bar"')
    >>> # You can do simple comparisons between marker objects:
    >>> Marker("python_version > '3.6'") == Marker("python_version > '3.6'")
    True
    >>> # You can also perform simple comparisons between sets of markers:
    >>> markers1 = {Marker("python_version > '3.6'"), Marker('os_name == "unix"')}
    >>> markers2 = {Marker('os_name == "unix"'), Marker("python_version > '3.6'")}
    >>> markers1 == markers2
    True

When evaluating a marker for a set of candidate extras, pass the set with the
keyword-only ``extras`` argument. The complete marker expression is evaluated
independently for each candidate, and the result is ``True`` if any candidate
matches. Extra names are normalized according to PEP 685; an empty set
returns ``False``. When both ``extras`` and ``environment['extra']`` are
provided, the candidate set takes precedence over the scalar environment value.
This argument is separate from the set-valued ``extras`` and
``dependency_groups`` marker names used with membership operators.

This is useful when checking a dependency marker against the extras requested
by a :class:`~packaging.requirements.Requirement`:

.. doctest::

    >>> from packaging.requirements import Requirement
    >>> requested = Requirement("a[b,c]")
    >>> dependency = Requirement("foo; extra == 'b'")
    >>> dependency.marker.evaluate(extras=requested.extras)
    True

Combining markers programmatically
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

:class:`Marker` objects support the ``&`` (and) and ``|`` (or) operators for
combining markers without manually constructing marker strings:

.. doctest::

    >>> from packaging.markers import Marker
    >>> py3 = Marker("python_version >= '3'")
    >>> linux = Marker("sys_platform == 'linux'")
    >>> combined = py3 & linux
    >>> str(combined)
    'python_version >= "3" and sys_platform == "linux"'
    >>> either = py3 | linux
    >>> str(either)
    'python_version >= "3" or sys_platform == "linux"'

This is equivalent to writing the combined marker string directly but is useful
when building markers dynamically from separate conditions.

.. versionadded:: 26.1


Reference
---------

.. automodule:: packaging.markers
    :members:
    :special-members: __and__, __or__
    :exclude-members: __init__
