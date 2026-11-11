Filenames
=========

Tools to work with filenames for SDists and wheels.

.. versionadded:: 26.4

Working with filenames
----------------------

Filenames are handled in two stages. Each stage has its own class:

* :class:`~packaging.filenames.WheelFilename` and
  :class:`~packaging.filenames.SourceDistributionFilename` hold the parts of a
  filename as strings, exactly as they are written.
* :class:`~packaging.filenames.NormalizedWheelFilename` and
  :class:`~packaging.filenames.NormalizedSdistFilename` hold the
  parsed and normalized parts.

To split a filename into its parts, use ``.from_filename``. Then call
``.normalize()`` to parse the parts:

.. doctest::

   >>> from packaging.filenames import WheelFilename
   >>> raw = WheelFilename.from_filename("Foo.Bar-01.0-1-py3-none-any.whl")
   >>> raw.name, raw.version, raw.build_tag, raw.tags
   ('Foo.Bar', '01.0', '1', 'py3-none-any')
   >>> wheel = raw.normalize()
   >>> wheel.name, wheel.version, wheel.build_tag
   ('foo-bar', <Version('1.0')>, (1, ''))
   >>> str(wheel)
   'foo_bar-1.0-1-py3-none-any.whl'

``.from_filename`` only checks the structure of the filename: the extension and
the number of parts. ``.normalize()`` checks each part, and raises
:class:`~packaging.filenames.InvalidWheelFilename` or
:class:`~packaging.filenames.InvalidSdistFilename` if a part is not valid.

``.normalize()`` accepts legacy filenames that are not normalized. To require a
normalized filename, use ``.normalize(strict=True)``. It collects all
normalization problems into an :external:exc:`ExceptionGroup`. Each problem
has its own exception class, so you can use ``except*`` to handle or ignore
only some of them. The classes are:

* :class:`~packaging.filenames.InvalidProjectName`: the name parses, but is
  not a valid project name.
* :class:`~packaging.filenames.NonNormalizedName`: the name is valid, but not
  normalized.
* :class:`~packaging.filenames.NonNormalizedVersion`: the version is valid,
  but not normalized.
* :class:`~packaging.filenames.ZipSdistFilename` (sdist only): the legacy
  ``.zip`` was used instead of ``.tar.gz``.
* :class:`~packaging.filenames.NonNormalizedBuildTag` (wheel only): the build
  tag is valid, but not normalized.
* :class:`~packaging.filenames.UnsortedWheelTags` (wheel only): the parts of
  the compressed tag set are not in sorted order.
* :class:`~packaging.filenames.NonNormalizedTags` (wheel only): the tags are
  sorted, but not normalized.

Each normalization message gives the expected value. The group message gives
the full normalized filename, unless the project name is not valid.

For example, to accept a non-normalized name and version, but reject all other
problems:

.. code-block:: python

    from packaging.filenames import (
        NonNormalizedName,
        NonNormalizedVersion,
        WheelFilename,
    )

    raw = WheelFilename.from_filename("Foo-01.0-py3-none-any.whl")
    try:
        wheel = raw.normalize(strict=True)
    except* (NonNormalizedName, NonNormalizedVersion):
        wheel = raw.normalize()

On Python 3.10, catch the :class:`~packaging.errors.ExceptionGroup` backport
and process it directly (see :doc:`errors`).

The classes shared by sdists and wheels
(:class:`~packaging.filenames.InvalidProjectName`,
:class:`~packaging.filenames.NonNormalizedName`, and
:class:`~packaging.filenames.NonNormalizedVersion`) are subclasses of
:class:`~packaging.filenames.InvalidFilename` only. They are not subclasses of
:class:`~packaging.filenames.InvalidSdistFilename` or
:class:`~packaging.filenames.InvalidWheelFilename`. To match every problem, use
``except* InvalidFilename``.

An invalid part raises one exception. A filename that is not normalized raises
a group, and only with ``strict=True``.

Using filenames
---------------

The filename classes have these properties. All of them are strings, as
written in the filename:

* ``name`` and ``version``.
* ``tags`` (wheel only): The compressed tag string, like ``py2.py3-none-any``.
* ``build_tag`` (wheel only): The build tag, or ``None``.
* ``variant`` (wheel only): The variant label, or ``None``.
* ``extension`` (sdist only): ``.tar.gz`` or the legacy ``.zip``.

The normalized classes have these properties:

* ``name``: The normalized name.
* ``version``: The version as a :class:`~packaging.version.Version`.
* ``tags`` (wheel only): A frozenset of :class:`~packaging.tags.Tag`.
* ``build_tag`` (wheel only): An empty tuple, or a tuple of (build number,
  build tag suffix). The suffix can be an empty string.
* ``variant`` (wheel only): The variant label, or ``None``.
* ``compressed_tags`` (wheel only): The sorted, compressed wheel tags as a
  string.
* ``build_str`` (wheel only): The build tag as a string, or an empty string.

The ``.dist-info`` directory in a wheel has the same name and version as the
wheel filename. A tool that renames a wheel must not change the name or version
unless it also renames that directory. To change only the tags, replace them in
the filename class, which keeps the other parts as written:

.. doctest::

    >>> from packaging.filenames import WheelFilename
    >>> old = WheelFilename.from_filename("Foo.Bar-1.0-1-py3-none-any.whl")
    >>> new = old.__replace__(tags="py2.py3-none-any")
    >>> str(new)
    'Foo.Bar-1.0-1-py2.py3-none-any.whl'

All four classes are immutable, and support most operations that you would
expect:

* Use :func:`copy.replace` (Python 3.13+) or ``__replace__`` to replace parts
  of the filename.
* Equality and hashing work. Two filenames are equal if their strings are
  equal. Two normalized filenames are equal if their parts are equal. The
  number of trailing zeros in the version is significant, so ``1.0`` and
  ``1.0.0`` are different.
* Pickling and unpickling are supported in a stable format.
* Converting to a string (or ``.to_filename()``) produces the filename. For a
  filename class, this is the filename as written. For a normalized class, it
  is the fully normalized filename with the standard extension (``.whl`` or
  ``.tar.gz``).

The constructors take the same parts as the properties. The constructor of a
filename class only checks that the parts make a filename that splits into the
same parts. The constructor of a normalized class checks the parts.

Converting from older utils
---------------------------

The older :func:`packaging.utils.parse_wheel_filename` does not support
variant labels (:pep:`825`).

.. warning::

    :func:`~packaging.utils.parse_wheel_filename` rejects variant wheels, and
    ``WheelFilename.from_filename`` accepts them. If your code cannot process
    variant wheels, check that ``.variant`` is ``None`` after you parse.

To support variant labels, replace the old form:

.. doctest::

    >>> from packaging.utils import parse_wheel_filename
    >>> name, version, build_tag, tags = parse_wheel_filename(
    ...     "foo-1.0-1-py3-none-any.whl"
    ... )

with:

.. doctest::

    >>> from packaging.filenames import WheelFilename
    >>> wheel = WheelFilename.from_filename("foo-1.0-1-py3-none-any.whl").normalize()
    >>> name, version, build_tag, tags = (
    ...     wheel.name, wheel.version, wheel.build_tag, wheel.tags
    ... )
    >>> wheel.variant is None
    True

To replace ``validate_order=True``, call
:meth:`WheelFilename.normalize(strict=True) <packaging.filenames.WheelFilename.normalize>`.
It reports unsorted tags with
:class:`~packaging.filenames.UnsortedWheelTags`. It also checks that the other
parts of the filename are normalized. To check only the tag order and
reject variant wheels, like ``parse_wheel_filename(..., validate_order=True)``,
this time showing Python 3.10+ compatible syntax:

.. testcode::

    import sys

    from packaging.filenames import (
        InvalidWheelFilename,
        NormalizedWheelFilename,
        UnsortedWheelTags,
        WheelFilename,
    )

    if sys.version_info < (3, 11):
        from packaging.errors import ExceptionGroup


    def parse_ordered(filename: str) -> NormalizedWheelFilename:
        raw = WheelFilename.from_filename(filename)
        try:
            wheel = raw.normalize(strict=True)
        except ExceptionGroup as group:
            for error in group.exceptions:
                if isinstance(error, UnsortedWheelTags):
                    raise error from None
            wheel = raw.normalize()
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
