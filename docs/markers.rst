Markers
=======

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

You can combine existing :class:`Marker` instances with ``&`` and ``|`` instead of
parsing one long marker string. The string form preserves PEP 508 ``and`` / ``or``
precedence. :meth:`Marker.as_ast` returns an immutable tree of
:class:`MarkerCompare`, :class:`MarkerAnd`, and :class:`MarkerOr` nodes (see
:class:`MarkerNode`).

.. doctest::

    >>> from packaging.markers import Marker, MarkerCompare, MarkerAnd, MarkerOr
    >>> py_at_least_310 = Marker('python_version >= "3.10"')
    >>> posix = Marker('os_name == "posix"')
    >>> py_at_least_310 & posix
    <Marker('python_version >= "3.10" and os_name == "posix"')>
    >>> windows = Marker('sys_platform == "win32"')
    >>> macos = Marker('sys_platform == "darwin"')
    >>> windows | macos
    <Marker('sys_platform == "win32" or sys_platform == "darwin"')>
    >>> expr = Marker(
    ...     "python_version > '3.12' or (python_version == '3.12' and os_name == 'unix')"
    ... )
    >>> node = expr.as_ast()
    >>> isinstance(node, MarkerOr)
    True
    >>> len(node.operands)
    2
    >>> isinstance(node.operands[0], MarkerCompare)
    True
    >>> (node.operands[0].left, node.operands[0].op, node.operands[0].right)
    ('python_version', '>', '3.12')
    >>> isinstance(node.operands[1], MarkerAnd)
    True
    >>> [type(p).__name__ for p in node.operands[1].operands]
    ['MarkerCompare', 'MarkerCompare']

.. versionadded:: 26.1

Reference
---------

.. automodule:: packaging.markers
    :members:
    :special-members: __and__, __or__
    :exclude-members: __init__

.. autodata:: MarkerCompareOp
    :no-value:
