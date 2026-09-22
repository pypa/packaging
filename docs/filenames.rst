Filenames
=========

Tools to work with filenames for SDists and wheels.

.. versionadded:: 26.4

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
    >>> wheel = WheelFilename.from_filename(
    ...     "foo-1.0-1-py3-none-any.whl", strict=False
    ... )
    >>> name, version, build_tag, tags = (
    ...     wheel.name, wheel.version, wheel.build_tag, wheel.tags
    ... )
    >>> wheel.variant is None
    True

Be sure to check and handle :attr:`~packaging.filenames.WheelFilename.variant`.
``validate_order=True`` will throw an error if the tag order is not sorted,
just like the old function. The new ``strict=True`` parameter will require
a normalized filename.

Reference
---------

.. automodule:: packaging.filenames
    :members:
    :inherited-members:
