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
    >>> metadata = "Metadata-Version: 2.3\nName: packaging\nVersion: 24.0"
    >>> raw, unparsed = parse_email(metadata)
    >>> raw["metadata_version"]
    '2.3'
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
