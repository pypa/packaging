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

    >>> from packaging.tags import Tag, sys_tags
    >>> import sys
    >>> looking_for = Tag("py{major}".format(major=sys.version_info.major), "none", "any")
    >>> supported_tags = list(sys_tags())
    >>> looking_for in supported_tags
    True
    >>> really_old = Tag("py1", "none", "any")
    >>> wheels = {really_old, looking_for}
    >>> best_wheel = None
    >>> for supported_tag in supported_tags:
    ...     for wheel_tag in wheels:
    ...         if supported_tag == wheel_tag:
    ...             best_wheel = wheel_tag
    ...             break
    >>> best_wheel == looking_for
    True

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



Low Level Interface
'''''''''''''''''''

The following functions are low-level implementation details. They should typically not
be needed in application code, unless the application has specialised requirements (for
example, constructing sets of supported tags for environments other than the running
interpreter).

These functions capture the precise details of which environments support which tags. That
information is not defined in the compatibility tag standards but is noted as being up
to the implementation to provide.


.. attribute:: INTERPRETER_SHORT_NAMES

    A dictionary mapping interpreter names to their `abbreviation codes`_
    (e.g. ``"cpython"`` is ``"cp"``). All interpreter names are lower-case.


.. autofunction:: interpreter_name

.. autofunction:: interpreter_version

.. autofunction:: mac_platforms

.. autofunction:: ios_platforms

.. autofunction:: android_platforms

.. autofunction:: platform_tags

.. autofunction:: compatible_tags

.. autofunction:: cpython_tags

.. autofunction:: generic_tags


.. _`abbreviation codes`: https://www.python.org/dev/peps/pep-0425/#python-tag
.. _`compressed tag set`: https://www.python.org/dev/peps/pep-0425/#compressed-tag-sets
.. _`platform compatibility tags`: https://packaging.python.org/specifications/platform-compatibility-tags/
