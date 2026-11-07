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


.. _metadata-validation-policies:

Application validation policies
-------------------------------

Applications can add requirements beyond the core metadata specification by
passing ``validation_policy=policy`` to :meth:`Metadata.from_raw` or
:meth:`Metadata.from_email`. A policy is an object with any of the following
optional methods:

* ``validate_FIELD(value)``, where ``FIELD`` is a :class:`Metadata` attribute
  name, such as ``version`` or ``requires_dist``. The method receives the value
  after the built-in conversion and validation: for example, a
  :class:`~packaging.version.Version` rather than a version string. Absent
  optional fields receive ``None``, allowing an application to require them.
  A method is not called when that field fails built-in validation.
* ``full_validate(metadata)`` for checks involving multiple fields. This method
  receives the :class:`Metadata` instance after all field checks succeed.

Methods must return ``None`` on success. To reject metadata, raise
:class:`InvalidMetadata`, using the email field name, such as
``"requires-python"``, or raise :class:`~packaging.errors.ExceptionGroup`
containing only ``InvalidMetadata`` exceptions. Nested validation groups are
supported. Returning an error or any other non-``None`` value raises
:class:`TypeError`. Other exceptions, including groups containing programming
errors, propagate without being treated as invalid metadata.

.. doctest::

    >>> from packaging.metadata import InvalidMetadata, Metadata
    >>> from packaging.version import Version
    >>> class IndexPolicy:
    ...     def validate_version(self, value: Version) -> None:
    ...         if value.local is not None:
    ...             raise InvalidMetadata("version", "Local versions are not accepted")
    ...
    ...     def full_validate(self, metadata: Metadata) -> None:
    ...         if metadata.name.startswith("internal-") and not metadata.summary:
    ...             raise InvalidMetadata("summary", "Internal projects need a summary")
    >>> metadata = Metadata.from_email(
    ...     "Metadata-Version: 2.4\nName: example\nVersion: 1.0+private\n",
    ...     validate=False,
    ...     validation_policy=IndexPolicy(),
    ... )
    >>> metadata.version
    Traceback (most recent call last):
        ...
    packaging.metadata.InvalidMetadata: Local versions are not accepted

With ``validate=True`` (the default), built-in and policy errors from individual
fields are collected together. :meth:`Metadata.from_email` also collects email
parsing errors. A policy cannot disable built-in validation: rejecting a
supported metadata version, for example, does not prevent checking whether
other fields are allowed in that version.

``full_validate`` runs only if parsing, built-in field checks, and field policy
checks all succeed. It is skipped after any of those errors, so cross-field
errors are not reported alongside existing field errors. This gives the
cross-field method valid field values without requiring it to handle a
partially invalid object.

With ``validate=False``, each field's built-in and policy checks run when the
attribute is first accessed. Successful values are cached, while failures
are retried on subsequent access. ``full_validate`` does not run in this mode,
even after all attributes have been read. As with ordinary deferred metadata
validation, checks that depend on the metadata version run only when
``validate=True``.

Policies apply to the instance created by that factory call. They must not
modify the values or metadata passed to them, and should not change their rules
after validation begins because successful values are cached. Field validation
order is unspecified. Pickling an instance also pickles its policy; the policy
must therefore be picklable. Serializing to email stores metadata values only,
so pass the policy again when reading them if validation is required.


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
