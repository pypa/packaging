Wheel Files
===========

.. currentmodule:: packaging.wheelfile

Read and write `wheel files`_. The reader checks each file against the
``RECORD`` file as it is read. The writer computes ``RECORD`` as files are
added and generates the ``WHEEL`` file from the wheel's name.

.. versionadded:: 26.4

Usage
-----

Write a wheel by name. The name, version, build tag and tags come from the
filename, and ``WHEEL`` and ``RECORD`` are generated when the context exits:

.. code-block:: python

    from packaging.wheelfile import WheelWriter

    with WheelWriter("example-1.0-py3-none-any.whl", generator="mytool 1.0") as writer:
        writer.write_file("example/__init__.py", b"print('hello')\n")
        writer.write_data_file("scripts/example", b"#!python\n", mode=0o755)
        writer.write_dist_info_file("METADATA", metadata_bytes)

A file object can be used instead of a path. The wheel name must then be given
as :class:`WheelMetadata`, since there is no filename to parse. The same applies
to reading:

.. doctest::

    >>> from io import BytesIO
    >>> from packaging.wheelfile import WheelMetadata, WheelReader, WheelWriter
    >>> buffer = BytesIO()
    >>> metadata = WheelMetadata.from_filename("example-1.0-py3-none-any.whl")
    >>> with WheelWriter(buffer, generator="mytool 1.0", metadata=metadata) as writer:
    ...     writer.write_file("example/__init__.py", b"print('hello')\n")
    ...     writer.write_dist_info_file("METADATA", b"Metadata-Version: 2.4\nName: example\nVersion: 1.0\n")
    >>> with WheelReader(buffer) as reader:
    ...     (reader.name, str(reader.version))
    ...     reader.dist_info_dir
    ...     reader.validate_record()
    ...     reader.read_file("example/__init__.py")
    ...     print(reader.read_dist_info_file("WHEEL").decode())
    ('example', '1.0')
    'example-1.0.dist-info'
    b"print('hello')\n"
    Wheel-Version: 1.0
    Generator: mytool 1.0
    Root-Is-Purelib: true
    Tag: py3-none-any
    <BLANKLINE>
    <BLANKLINE>

Reading a file that does not match ``RECORD`` raises :exc:`WheelError`:

.. doctest::

    >>> from zipfile import ZipFile
    >>> with ZipFile(buffer, "a") as zf:
    ...     zf.writestr("extra.txt", "not in RECORD")
    >>> with WheelReader(buffer) as reader:
    ...     reader.read_file("extra.txt")
    Traceback (most recent call last):
        ...
    packaging.wheelfile.WheelError: No hash found for file 'extra.txt'

Reproducible wheels
-------------------

Every archive member has a timestamp and permission bits. By default, members
written from bytes or file objects get mode ``0o664`` and the timestamp
1980-01-01, the earliest the ZIP format can store. Members written from a path
keep the permissions of the file on disk. The ``timestamp`` and ``mode``
arguments of :class:`WheelWriter` change the defaults for every member,
including the generated ``WHEEL`` and ``RECORD`` files, and the same arguments
on each write method override them for one member.

If the ``SOURCE_DATE_EPOCH`` environment variable is set when a
:class:`WheelWriter` is created and no ``timestamp`` is given, its value is
used as the default timestamp. Timestamps outside the range the ZIP format can
store are clamped to that range.

Reference
---------

.. autoclass:: WheelWriter
    :members:

.. autofunction:: write_wheelfile

.. autoclass:: WheelReader
    :members:

.. autoclass:: WheelArchiveFile
    :members:

.. autoclass:: WheelMetadata
    :members:

.. autoclass:: WheelRecordEntry
    :members:

.. autoclass:: WheelContentElement
    :members:

.. autoclass:: WheelError


.. _wheel files: https://packaging.python.org/en/latest/specifications/binary-distribution-format/
