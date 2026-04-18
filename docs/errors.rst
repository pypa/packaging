Errors
======

Error classes and error-handling helpers used by the packaging library.

Currently this contains :class:`~packaging.errors.ExceptionGroup`, a simple
backport of the stdlib :class:`ExceptionGroup`. It is recommended to use
the stdlib module on Python 3.11+, but this does reexport that as well.

Recommended Usage
-----------------


.. code-block:: python

   if sys.version_info < (3, 11):
       from packaging.errors import ExceptionGroup

   try:
       ...
   except ExceptionGroup as err:
       for error in err.exceptions:
           ...


Reference
---------

.. This has to be listed here so building it on newer Python keeps the docs

.. py:class:: packaging.errors.ExceptionGroup(message: str, exceptions: list[Exception])

   On older Pythons, this is a small fallback implementation of the
   :class:`ExceptionGroup` introduced in Python 3.11.

   :param message: The message for the group.
   :param exceptions: A list of exceptions contained in the group.

   Attributes
   ----------

   message (str)
       The message passed to the group.

   exceptions (list[Exception])
       The exceptions contained in the group.


.. automodule:: packaging.errors
   :members:
   :exclude-members: ExceptionGroup
