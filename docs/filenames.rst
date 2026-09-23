Filenames
=========

Tools to work with filenames for SDists and wheels.

.. versionadded:: 26.4

Working with filenames
----------------------

To parse a filename, use ``.from_filename`` on
:class:`~packaging.filenames.WheelFilename` or
:class:`~packaging.filenames.SourceDistributionFilename`:

.. doctest::

   >>> from packaging.filenames import WheelFilename
   >>> wheel_filename = WheelFilename.from_filename("foo-1.0-1-py3-none-any.whl")

A wheel filename with six parts is ambiguous: the extra part is either a
build tag or a variant label (:pep:`825`). A build tag must start with a
digit, and a Python tag never does, so a third part that starts with a digit
is a build tag. Otherwise, the last part is a variant label. For example,
``foo-1.0-abc-py3-none-any.whl`` has the tag ``abc-py3-none`` and the variant
label ``any``.

Parsing normalizes filenames. To ensure a filename is already normalized,
call ``.validate()`` on the parsed filename. It collects all normalization
problems into an :external:exc:`ExceptionGroup`. Each problem has its own exception class, such
as :class:`~packaging.filenames.NonNormalizedName` for a valid name that is not
normalized and :class:`~packaging.filenames.InvalidProjectName` for a name that
parses but is not a valid project name, so
you can use ``except*`` to handle or ignore only some of them. For example, to
accept a non-normalized name and version, but reject all other problems:

.. code-block:: python

    from packaging.filenames import (
        NonNormalizedName,
        NonNormalizedVersion,
        WheelFilename,
    )

    wheel = WheelFilename.from_filename("Foo-01.0-py3-none-any.whl")
    try:
        wheel.validate()
    except* (NonNormalizedName, NonNormalizedVersion):
        pass

On Python 3.10, catch the :class:`~packaging.errors.ExceptionGroup` backport
and process it directly (see :doc:`errors`).

Using filenames
---------------

Filenames have the following properties:

* ``name``: The normalized name.
* ``version``: The version as a :class:`~packaging.version.Version`.
* ``tags`` (wheel only): A frozenset of :class:`~packaging.tags.Tag`.
* ``build_tag`` (wheel only): An empty tuple, or a tuple of (build number,
  build tag suffix). The suffix can be an empty string.
* ``variant`` (wheel only): The variant label, or ``None``.

There are also a few helper properties for wheels:

* ``compressed_tags``: The sorted, compressed wheel tags as a string.
* ``build_str``: The build tag as a string, or an empty string.

The immutable classes support most operations that you would expect:

* Use :func:`copy.replace` (Python 3.13+) or ``__replace__`` to replace parts
  of the filename.
* Equality and hashing work. The number of trailing zeros in the version is
  significant, so ``1.0`` and ``1.0.0`` are different. The original filename
  is not compared, so a parsed filename can be equal to one that fails
  ``.validate()``.
* Pickling and unpickling are supported, and the pickle format is stable.
  A pickle keeps the original filename, so ``.validate()`` gives the same
  result after unpickling. A filename that is constructed or changed with
  ``__replace__`` has no original filename, and ``.validate()`` always
  passes.
* Converting to a string (or ``.to_filename()``) produces a fully normalized
  filename with the standard extension (``.whl`` or ``.tar.gz``).

Converting from older utils
---------------------------

The older :func:`packaging.utils.parse_wheel_filename` does not support
variant labels (:pep:`825`). To support them, replace the old form:

.. doctest::

    >>> from packaging.utils import parse_wheel_filename
    >>> name, version, build_tag, tags = parse_wheel_filename(
    ...     "foo-1.0-1-py3-none-any.whl"
    ... )

with:

.. doctest::

    >>> from packaging.filenames import WheelFilename
    >>> wheel = WheelFilename.from_filename("foo-1.0-1-py3-none-any.whl")
    >>> name, version, build_tag, tags = (
    ...     wheel.name, wheel.version, wheel.build_tag, wheel.tags
    ... )
    >>> wheel.variant is None
    True

To replace ``validate_order=True``, call
:meth:`WheelFilename.validate() <packaging.filenames.WheelFilename.validate>`.
It reports unsorted tags with
:class:`~packaging.filenames.UnsortedWheelTags`. It also checks that the other
parts of the filename are normalized. To check only the tag order and
reject variant wheels, like ``parse_wheel_filename(..., validate_order=True)``,
this time showing Python 3.10+ compatible syntax:

.. testcode::

    import sys

    from packaging.filenames import (
        InvalidWheelFilename,
        UnsortedWheelTags,
        WheelFilename,
    )

    if sys.version_info < (3, 11):
        from packaging.errors import ExceptionGroup


    def parse_ordered(filename: str) -> WheelFilename:
        wheel = WheelFilename.from_filename(filename)
        try:
            wheel.validate()
        except ExceptionGroup as group:
            for error in group.exceptions:
                if isinstance(error, UnsortedWheelTags):
                    raise error from None
        if wheel.variant is not None:
            msg = f"Invalid wheel filename (variant wheels are not supported): {filename!r}"
            raise InvalidWheelFilename(msg)
        return wheel

.. doctest::

    >>> parse_ordered("Foo-1.0-py3.py2-none-any.whl")
    Traceback (most recent call last):
        ...
    packaging.filenames.UnsortedWheelTags: Invalid wheel filename (compressed tag set components must be in sorted order per PEP 425): 'Foo-1.0-py3.py2-none-any.whl'
    >>> parse_ordered("foo-1.0-py3-none-any-x86_64_v3.whl")
    Traceback (most recent call last):
        ...
    packaging.filenames.InvalidWheelFilename: Invalid wheel filename (variant wheels are not supported): 'foo-1.0-py3-none-any-x86_64_v3.whl'
    >>> str(parse_ordered("foo-1.0-py2.py3-none-any.whl"))
    'foo-1.0-py2.py3-none-any.whl'

Reference
---------

.. automodule:: packaging.filenames
    :members:
    :inherited-members:
