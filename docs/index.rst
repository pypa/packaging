Welcome to packaging
====================

.. include:: ../README.rst
   :start-after: start-intro
   :end-before: end-intro


Installation
------------

You can install packaging with ``pip``:

.. code-block:: console

    $ pip install packaging

The ``packaging`` library uses calendar-based versioning (``YY.N``).

Online Validator
----------------

If you want to quickly test version strings, requirements, or specifiers without installing the library, you can use our `online validator <https://pypa.github.io/packaging/validator/>`_. This web-based tool runs in your browser using Pyodide and uses the latest version of packaging from PyPI.

The online validator is particularly useful for:

- Quick validation of version strings and requirements
- Understanding PEP 440 version specification
- Debugging version comparison issues
- Learning requirement syntax without installation

You can also run the validator locally by opening the ``web_validator/index.html`` file in your web browser.


.. toctree::
    :maxdepth: 1
    :caption: API Documentation
    :hidden:

    version
    specifiers
    ranges
    markers
    licenses
    requirements
    metadata
    tags
    pylock
    direct_url
    dependency_groups
    errors
    utils

.. toctree::
    :maxdepth: 1
    :caption: Tools
    :hidden:

    validator

.. toctree::
    :maxdepth: 2
    :caption: Project
    :hidden:

    development/index
    security
    changelog
