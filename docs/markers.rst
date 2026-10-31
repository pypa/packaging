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

Evaluating many markers against one environment
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

:func:`prepare_environment` applies the same defaults, context and overrides
as :meth:`Marker.evaluate`. Use it once when evaluating many markers against
one environment:

.. doctest::

    >>> from packaging.markers import Marker, prepare_environment
    >>> environment = prepare_environment({"os_name": "posix"})
    >>> markers = [Marker("os_name == 'posix'"), Marker("os_name == 'nt'")]
    >>> [marker.evaluate_prepared(environment) for marker in markers]
    [True, False]

The returned dict is mutable. If changing ``extra`` between evaluations,
normalize its value with :func:`packaging.utils.canonicalize_name` first:

.. doctest::

    >>> from packaging.utils import canonicalize_name
    >>> marker = Marker('extra == "fancy-feature"')
    >>> environment["extra"] = canonicalize_name("Fancy.Feature")
    >>> marker.evaluate_prepared(environment)
    True

:meth:`Marker.evaluate_prepared` also accepts a caller-built mapping. It does
not fill missing keys from the host, add context defaults, normalize ``extra``
or repair ``python_full_version``. A referenced key missing from the mapping
raises :class:`UndefinedEnvironmentName`:

.. doctest::

    >>> Marker("sys_platform == 'linux'").evaluate_prepared({"sys_platform": "linux"})
    True

Overrides in :func:`prepare_environment` are independent. When targeting another
interpreter, supply both ``python_version`` and ``python_full_version``.

.. versionadded:: 26.4


Reference
---------

.. automodule:: packaging.markers
    :members:
    :special-members: __and__, __or__
    :exclude-members: __init__
