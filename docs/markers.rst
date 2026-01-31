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


Reference
---------

.. class:: Marker(markers)

    This class abstracts handling markers for dependencies of a project. It can
    be passed a single marker or multiple markers that are ANDed or ORed
    together. Each marker will be parsed according to the specification.

    :param str markers: The string representation of a marker or markers.
    :raises InvalidMarker: If the given ``markers`` are not parseable, then
                           this exception will be raised.

    .. method:: evaluate(environment=None, context='metadata')

    Evaluate the marker given the context of the current Python process.

    :param dict environment: A dictionary containing keys and values to
                             override the detected environment.
    :param EvaluateContext context: A string representing the context in which
                                    the marker is evaluated.
    :raises: UndefinedComparison: If the marker uses a comparison on strings
                                  which are not valid versions per the
                                  :ref:`specification of version specifiers
                                  <pypug:version-specifiers>`.
    :raises: UndefinedEnvironmentName: If the marker accesses a value that
                                       isn't present inside of the environment
                                       dictionary.
    :rtype: bool

.. autotypeddict:: packaging.markers.Environment

    A dictionary that represents a Python environment as captured by
    :func:`default_environment`.

.. py:data:: packaging.markers.EvaluateContext

    A ``typing.Literal`` enumerating valid values for the ``context`` passed to ``Marker.evaluate``, namely:

    * "metadata" (for core metadata; default)
    * "lock_file" (for lock files)
    * "requirement" (i.e. all other situations)

.. function:: default_environment()

    Returns a dictionary representing the current Python process. This is the
    base environment that is used when evaluating markers in
    :meth:`Marker.evaluate`.

    :rtype: Environment

 .. function:: format_full_version(info)

    Formats a Python version from a ``sys.version_info``-like object.

    :param info: An object with ``major``, ``minor``, ``micro``,
                 ``releaselevel`` and ``serial`` attributes.
    :rtype: str

.. exception:: InvalidMarker

    Raised when attempting to create a :class:`Marker` with a string that
    does not conform to the specification.


.. exception:: UndefinedComparison

    Raised when attempting to evaluate a :class:`Marker` with a
    comparison operator against values that are not valid
    versions per the :ref:`specification of version specifiers
    <pypug:version-specifiers>`.


.. exception:: UndefinedEnvironmentName

    Raised when attempting to evaluate a :class:`Marker` with a value that is
    missing from the evaluation environment.
