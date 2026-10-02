Online Validator
===============

The packaging library provides an online validator that allows you to test and validate version strings, requirements, and specifiers directly in your web browser without installing the library.

.. _validator-url: https://pypa.github.io/packaging/validator/

Access the validator at: https://pypa.github.io/packaging/validator/

Features
--------

The online validator provides three main validation tools:

**Version Validator**
- Parse and validate version strings according to PEP 440
- Display version components (epoch, release, pre, post, dev, local)
- Show normalized version representation
- Identify pre-releases, post-releases, and dev releases

**Requirement Validator**
- Validate requirement strings
- Extract requirement components (name, specifier, URL, marker, extras)
- Help debug requirement parsing issues
- Understand complex requirement syntax

**Specifier Validator**
- Validate version specifiers
- Test if specific versions match a specifier
- Support all PEP 440 specifier operators (>=, <=, >, <, ==, !=, ~=, ===)
- Understand specifier set combinations

Usage Examples
--------------

Version Validation
~~~~~~~~~~~~~~~~~

Valid version strings:

.. code-block:: text

    1.0.0              # Basic version
    2.1.3a1            # Alpha release
    3.0.0.post1        # Post release
    1!2.3.4            # Epoch version
    1.0.0.dev1         # Development release
    1.0.0+local        # Local version label

Invalid version strings will be rejected with detailed error messages.

Requirement Validation
~~~~~~~~~~~~~~~~~~~~~~

Valid requirement strings:

.. code-block:: text

    requests>=2.25.0           # Minimum version
    numpy~=1.20.0              # Compatible release
    django>=3.0,<4.0           # Version range
    package[extra]>=1.0        # With extras
    package @ https://...      # Direct URL reference

The validator will extract all components and display them in a structured format.

Specifier Validation
~~~~~~~~~~~~~~~~~~~~

Valid specifiers:

.. code-block:: text

    >=1.0.0                    # Greater than or equal
    ~=2.0.0                    # Compatible release
    >=3.0,<4.0                 # Combined specifiers
    !=1.5.0                    # Not equal to
    ===1.0.0                   # Exact match (including local)

You can optionally provide a test version to check if it matches the specifier.

How It Works
------------

The online validator uses `Pyodide <https://pyodide.org/>`_ to run Python code in the browser via WebAssembly. When you load the validator:

1. Pyodide is loaded from a CDN
2. A Python runtime is initialized in your browser
3. The latest version of the packaging library is installed from PyPI using micropip
4. Your input is processed using the actual packaging library
5. Results are displayed in real-time

This ensures that the validator always uses the current behavior of the packaging library, making it reliable for testing and debugging.

Local Usage
-----------

To run the validator locally:

1. Navigate to the ``web_validator`` directory in the packaging repository
2. Open ``index.html`` in your web browser
3. The validator will load automatically (requires internet connection for initial load)

Performance
-----------

- **Initial load**: 5-10 seconds (downloads Pyodide and packaging library)
- **Subsequent validations**: Nearly instant
- **Caching**: Browser caching reduces load times on repeat visits

Browser Compatibility
---------------------

The validator works in all modern browsers that support WebAssembly:

- Chrome/Edge 57+
- Firefox 52+
- Safari 11+
- Opera 44+

JavaScript must be enabled, and an internet connection is required for the initial load.

Use Cases
---------

The online validator is particularly useful for:

**Quick Testing**
- Test if a version string is valid without installing packaging
- Verify requirement syntax before adding to your project
- Check if a version matches a specifier

**Learning and Documentation**
- Understand PEP 440 version specification
- Learn requirement syntax and structure
- Explore different version formats

**Debugging**
- Debug version comparison issues
- Understand why a requirement fails to parse
- Validate complex specifiers

**Development**
- Test packaging library behavior
- Verify changes to version parsing
- Quick reference for version formats

Limitations
-----------

- Requires JavaScript to be enabled
- Requires internet connection for initial load
- Some advanced packaging features may not be available in browser environment
- Large requirements files may take longer to process

Contributing
------------

If you encounter issues with the online validator or have suggestions for improvements:

1. File an issue on the `packaging GitHub repository <https://github.com/pypa/packaging/issues>`_
2. Mention "online validator" in the issue title
3. Provide details about the problem or suggestion

The validator code is in the ``web_validator/`` directory of the packaging repository.