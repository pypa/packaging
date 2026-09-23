Filenames
=========

Tools to work with filenames for SDists and wheels.

.. versionadded:: 26.4

Working with filenames
----------------------

To construct a filename, use ``.from_filename`` on
:class:`~packaging.filenames.WheelFilename` or
:class:`~packaging.filenames.SourceDistributionFilename`:

.. doctest::

   >>> from packaging.filenames import WheelFilename
   >>> wheel_filename = WheelFilename.from_filename("foo-1.0-1-py3-none-any.whl")

Parsing normalizes non-normalized filenames. To require a normalized filename,
use :func:`~packaging.filenames.validate_wheel_filename` or
:func:`~packaging.filenames.validate_sdist_filename`. Like constructing a
filename, these raise :class:`~packaging.filenames.InvalidFilename` if the
filename is not valid. They collect all normalization problems into an
:external:exc:`ExceptionGroup`. Each problem has its own exception class, so
you can use ``except*`` to handle only some of them. For example, to accept a non-normalized name and version, but reject all other
problems:

.. code-block:: python

    from packaging.filenames import (
        NonNormalizedName,
        NonNormalizedVersion,
        validate_wheel_filename,
    )

    try:
        validate_wheel_filename("Foo-01.0-py3-none-any.whl")
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

The immutable classes support most operations as you'd expect:

* Use :func:`copy.replace` (Python 3.13+) or ``__replace__`` to replace parts
  of the filename.
* Equality and hashing work. The number of trailing zeros in the version is
  significant, so ``1.0`` and ``1.0.0`` are different.
* Pickling and unpickling are supported, and the pickle format is stable.
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

Be sure to check and handle :attr:`~packaging.filenames.WheelFilename.variant`.

To replace ``validate_order=True``, call
:func:`~packaging.filenames.validate_wheel_filename`. It reports unsorted tags
with :class:`~packaging.filenames.UnsortedWheelTags`. It also checks that the
other parts of the filename are normalized. To check only the tag order and
reject variant wheels, like ``parse_wheel_filename(..., validate_order=True)``:

.. testcode::

    import sys

    from packaging.filenames import (
        InvalidWheelFilename,
        UnsortedWheelTags,
        WheelFilename,
        validate_wheel_filename,
    )

    if sys.version_info < (3, 11):
        from packaging.errors import ExceptionGroup


    def parse_ordered(filename: str) -> WheelFilename:
        try:
            validate_wheel_filename(filename)
        except ExceptionGroup as group:
            for error in group.exceptions:
                if isinstance(error, UnsortedWheelTags):
                    raise error from None
        wheel = WheelFilename.from_filename(filename)
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
