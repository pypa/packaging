Tags
====

.. currentmodule:: packaging.tags

Wheels encode the Python interpreter, ABI, and platform that they support in
their filenames using `platform compatibility tags`_. This module provides
support for both parsing these tags as well as discovering what tags the
running Python interpreter supports.

Usage
-----

.. doctest::

    >>> from packaging.tags import Tag, create_compatible_tags_selector, sys_tags
    >>> import sys
    >>> looking_for = Tag("py{major}".format(major=sys.version_info.major), "none", "any")
    >>> supported_tags = list(sys_tags())
    >>> looking_for in supported_tags
    True
    >>> really_old = Tag("py1", "none", "any")
    >>> really_old in supported_tags
    False

Selecting wheels
''''''''''''''''

Supported tags are ordered from most to least preferred. To select compatible
wheels in that order, use :func:`create_compatible_tags_selector` with each
wheel's filename and the tag set returned by
:func:`~packaging.utils.parse_wheel_filename`. A wheel may have several tags;
its best matching tag determines its position. Incompatible wheels are omitted.

This example uses explicit target tags so the result is independent of the
machine running it. The platform-specific wheel is preferred over the universal
wheel, even though the universal wheel appears first in the input:

.. doctest::

    >>> from packaging.utils import parse_wheel_filename
    >>> target_tags = [
    ...     Tag("cp312", "cp312", "manylinux_2_17_x86_64"),
    ...     Tag("py3", "none", "any"),
    ... ]
    >>> select_wheels = create_compatible_tags_selector(target_tags)
    >>> filenames = [
    ...     "example-1.0-py2.py3-none-any.whl",
    ...     "example-1.0-cp312-cp312-manylinux_2_17_x86_64.whl",
    ...     "example-1.0-cp312-cp312-win_amd64.whl",
    ... ]
    >>> candidates = [
    ...     (filename, parse_wheel_filename(filename)[-1]) for filename in filenames
    ... ]
    >>> list(select_wheels(candidates))
    ['example-1.0-cp312-cp312-manylinux_2_17_x86_64.whl', 'example-1.0-py2.py3-none-any.whl']
    >>> best_wheel = next(select_wheels(candidates), None)
    >>> best_wheel
    'example-1.0-cp312-cp312-manylinux_2_17_x86_64.whl'
    >>> next(select_wheels([]), None) is None
    True
    >>> next(select_wheels(candidates[2:]), None) is None
    True

For the running interpreter, pass :func:`sys_tags` instead of ``target_tags``.
Take the first result to choose the preferred compatible wheel, or use ``None``
as the default to handle the case where no wheel matches. Continuing through
the supported tags after finding a match can replace a preferred wheel with a
less preferred one.

Reference
---------

High Level Interface
''''''''''''''''''''

The following functions are the main interface to the library, and are typically the only
items that applications should need to reference, in order to parse and check tags.

.. autoclass:: Tag
   :members:

.. autofunction:: parse_tag

.. autofunction:: sys_tags

.. autofunction:: create_compatible_tags_selector

.. autoexception:: TooManyTagsError

.. autoexception:: UnsortedTagsError

.. autoexception:: InvalidTag



Low Level Interface
'''''''''''''''''''

The following functions are low-level implementation details. They should typically not
be needed in application code, unless the application has specialised requirements (for
example, constructing sets of supported tags for environments other than the running
interpreter).

These functions capture the precise details of which environments support which tags. That
information is not defined in the compatibility tag standards but is noted as being up
to the implementation to provide.


.. autodata:: INTERPRETER_SHORT_NAMES


.. autodata:: PythonVersion

.. autodata:: AppleVersion


.. autofunction:: interpreter_name

.. autofunction:: interpreter_version

.. autofunction:: interpreter_abi

.. autofunction:: mac_platforms

.. autofunction:: ios_platforms

.. autofunction:: android_platforms

.. autofunction:: platform_tags

.. autofunction:: compatible_tags

.. autofunction:: pure_python_tags

.. autofunction:: cpython_tags

.. autofunction:: generic_tags


.. _`abbreviation codes`: https://www.python.org/dev/peps/pep-0425/#python-tag
.. _`compressed tag set`: https://www.python.org/dev/peps/pep-0425/#compressed-tag-sets
.. _`platform compatibility tags`: https://packaging.python.org/specifications/platform-compatibility-tags/
