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

Parsing accepts legacy filenames. To require a normalized filename, use
:func:`~packaging.filenames.validate_wheel_filename` or
:func:`~packaging.filenames.validate_sdist_filename`. These raise
:class:`~packaging.filenames.InvalidFilename` if the filename is not valid.
They collect all normalization problems into an
:external:exc:`ExceptionGroup`. Each problem has its own exception class, so you can use ``except*`` to handle only some of them. For
example, to accept a non-normalized name and version, but reject all other
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
other parts of the filename are normalized.

Reference
---------

.. automodule:: packaging.filenames
    :members:
    :inherited-members:
