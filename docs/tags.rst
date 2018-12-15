Tags
====

.. currentmodule:: packaging.tags

Wheels encode the Python interpreter, ABI, and platform that they support in
their filenames using *tags*. `PEP 425`_ specifies how to interpret these tags
as well as how to specify them in a wheel filename.

Usage
-----

.. doctest::

    >>> from packaging.tags import Tag, parse_wheel_filename, sys_tags
    >>> import sys
    >>> looking_for = Tag("py{major}".format(major=sys.version_info.major), "none", "any")
    >>> supported_tags = list(sys_tags())
    >>> looking_for in supported_tags
    True
    >>> really_old = parse_wheel_filename("oldie-3.14-py1-none-any.whl")
    >>> good_wheel = "current-1.0-{}.whl".format(str(looking_for))
    >>> current = parse_wheel_filename(good_wheel)
    >>> wheels = {really_old: "py1-none-any", current: good_wheel}
    >>> best_wheel = None
    >>> for supported_tag in supported_tags:
    ...     for wheel_tags, filename in wheels.items():
    ...         if supported_tag in wheel_tags:
    ...             best_wheel = filename
    ...             break
    >>> best_wheel == good_wheel
    True

Reference
---------

.. attribute:: INTERPRETER_SHORT_NAMES

    A dictionary mapping interpreter names to their `abbreviation codes`_
    (e.g. ``"cpython"`` is ``"cp"``). All interpreter names are lower-case.

.. class:: Tag(interpreter, abi, platform)

    A representation of the tag triple for a wheel. Instances are considered
    immutable and thus are hashable. Equality checking is also supported.

    :param str interpreter: The interpreter name, e.g. ``"py"``
                            (see :attr:`INTERPRETER_SHORT_NAMES` for mapping
                            well-known interpreter names to their short names).
    :param str abi: The ABI that a wheel supports, e.g. ``"cp37m"``.
    :param str platform: The OS/platform the wheel supports,
                         e.g. ``"win_amd64"``.

    .. attribute:: interpreter

        The interpreter name.

    .. attribute:: abi

        The supported ABI.

    .. attribute:: platform

        The OS/platform.


.. function:: parse_tag(tag)

    Parse the provided *tag* into a set of :class:`Tag` instances.

    The returning of a set is required due to the possibility that the tag is a
    `compressed tag set`_, e.g. ``"py2.py3-none-any"``.

    :param str tag: The tag to parse, e.g. ``"py3-none-any"``.


.. function:: parse_wheel_filename(path)

    Parse the *path* of a wheel file, returning a set of :class:`Tag` instances.

    A set is returned due to the possibility that the wheel filename represents
    a `compressed tag set`_. The path does not need to exist. The path may be
    an :class:`os.PathLike` object.

    :param typing.Union[str,os.PathLike] path: The path to a wheel file,
                                               e.g. ``"packaging-18.0-py2.py3-none-any.whl"``;
                                               the file does not need to exist.


.. function:: sys_tags()

    Create an iterable of tags that the running interpreter supports.

    The iterable is ordered so that the best-matching tag is first in the
    sequence. The exact preferential order to tags is interpreter-specific, but
    in general the tag importance is in the order of:

    1. Interpreter
    2. Platform
    3. ABI

    This order is due to the fact that an ABI is inherently tied to the
    platform, but platform-specific code is not necessarily tied to the ABI. The
    interpreter is the most important tag as it dictates basic support for any
    wheel.

    The function returns an iterable in order to allow for the possible
    short-circuiting of tag generation if the entire sequence is not necessary
    and calculating some tags happens to be expensive.


.. _abbreviation codes: https://www.python.org/dev/peps/pep-0425/#python-tag
.. _compressed tag set: https://www.python.org/dev/peps/pep-0425/#compressed-tag-sets
.. _PEP 425: https://www.python.org/dev/peps/pep-0425/
