Metadata
========

.. currentmodule:: packaging.metadata


Both `source distributions`_ and `binary distributions`_
(*sdists* and *wheels*, respectively) contain files recording the
`core metadata`_ for the distribution. This information is used for
everything from recording the name of the distribution to the
installation dependencies.


Usage
-----

.. doctest::

    >>> from packaging.metadata import parse_email
    >>> metadata = "Metadata-Version: 2.6\nName: packaging\nVersion: 24.0"
    >>> raw, unparsed = parse_email(metadata)
    >>> raw["metadata_version"]
    '2.6'
    >>> raw["name"]
    'packaging'
    >>> raw["version"]
    '24.0'
    >>> from packaging.metadata import Metadata
    >>> parsed = Metadata.from_raw(raw)
    >>> parsed.name
    'packaging'
    >>> parsed.version
    <Version('24.0')>


Selective validation
''''''''''''''''''''

:meth:`Metadata.from_raw` and :meth:`Metadata.from_email` validate every field
by default. If an application only relies on selected fields, it can disable
that eager pass and access the attributes it needs explicitly. This is useful
for otherwise usable legacy metadata containing a field introduced in a later
metadata version than the one declared.

.. doctest::

    >>> legacy = (
    ...     "Metadata-Version: 2.1\nName: example\n"
    ...     "Version: 1.0\nLicense-File: LICENSE"
    ... )
    >>> raw, unparsed = parse_email(legacy)
    >>> unparsed
    {}
    >>> metadata = Metadata.from_raw(raw, validate=False)
    >>> metadata.metadata_version
    '2.1'
    >>> metadata.name
    'example'
    >>> metadata.version
    <Version('1.0')>

Accessing an attribute still validates and converts that individual value. It
does not validate fields that are not accessed, collect all validation errors,
or perform the eager metadata-version eligibility checks. Callers should only
use this mode when they deliberately own validation of the fields they consume.

When malformed or unrecognized email headers matter, call :func:`parse_email`
directly and inspect its ``unparsed`` result, as above. That information is not
available from ``Metadata.from_email(..., validate=False)``.


Reference
---------

High Level Interface
''''''''''''''''''''

.. autoclass:: packaging.metadata.Metadata
    :members:

Low Level Interface
'''''''''''''''''''

.. autoclass:: packaging.metadata.RawMetadata
    :members:
    :undoc-members:

.. autofunction:: packaging.metadata.parse_email

.. autoclass:: packaging.metadata.RFC822Message

.. autoclass:: packaging.metadata.RFC822Policy


Exceptions
''''''''''

.. autoclass:: packaging.metadata.InvalidMetadata
    :members:

.. note::

    ``packaging.metadata.ExceptionGroup`` is a backward-compatible re-export
    of :class:`packaging.errors.ExceptionGroup` and is omitted here to avoid
    duplicate documentation. See :mod:`packaging.errors` for the canonical
    documentation.


.. _source distributions: https://packaging.python.org/en/latest/specifications/source-distribution-format/
.. _binary distributions: https://packaging.python.org/en/latest/specifications/binary-distribution-format/
.. _core metadata: https://packaging.python.org/en/latest/specifications/core-metadata/
