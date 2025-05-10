Metadata
========

.. currentmodule:: packaging.markers


Both `source distributions`_ and `binary distributions`_
(_sdists_ and _wheels_, respectively) contain files recording the
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

.. autofunction:: packaging.metadata.parse_email


Exceptions
''''''''''

.. autoclass:: packaging.metadata.InvalidMetadata
    :members:

.. autoclass:: packaging.metadata.ExceptionGroup
    :members:


.. _source distributions: https://packaging.python.org/en/latest/specifications/source-distribution-format/
.. _binary distributions: https://packaging.python.org/en/latest/specifications/binary-distribution-format/
.. _core metadata: https://packaging.python.org/en/latest/specifications/core-metadata/
