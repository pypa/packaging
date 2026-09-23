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
:func:`~packaging.filenames.validate_ordered_tags` before parsing. To require
a fully normalized filename, including sorted tags, call
:func:`~packaging.filenames.validate_wheel_filename` instead:

.. doctest::

    >>> from packaging.filenames import validate_ordered_tags
    >>> filename = "foo-1.0-1-py3-none-any.whl"
    >>> validate_ordered_tags(filename)
    >>> wheel = WheelFilename.from_filename(filename)

Reference
---------

.. automodule:: packaging.filenames
    :members:
    :inherited-members:
