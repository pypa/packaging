Online validator
================

Use these forms to check versions, requirements, and specifiers in your
browser. The forms run the packaging source code from this version of the
documentation in `Pyodide <https://pyodide.org/>`_. When you first use a
form, your browser downloads Python from the Pyodide CDN (approximately 7 MB).

.. raw:: html

    <p id="validator-status">Python is not loaded.</p>

Version
-------

Parse a version as specified in the :ref:`pypug:version-specifiers`
specification. See :class:`~packaging.version.Version`.

.. raw:: html

    <form class="validator" data-check="check_version">
      <input aria-label="Version" placeholder="1.0.post1" autocomplete="off">
      <button type="submit">Check</button>
      <output aria-live="polite"></output>
    </form>

Requirement
-----------

Parse a dependency specifier. See
:class:`~packaging.requirements.Requirement`.

.. raw:: html

    <form class="validator" data-check="check_requirement">
      <input aria-label="Requirement" placeholder="name[extra]>=1.0; python_version>'3.10'" autocomplete="off">
      <button type="submit">Check</button>
      <output aria-live="polite"></output>
    </form>

Specifier
---------

Parse a specifier set. If you also enter a version, the form shows if the
specifier set contains it. See :class:`~packaging.specifiers.SpecifierSet`.

.. raw:: html

    <form class="validator" data-check="check_specifier">
      <input aria-label="Specifier" placeholder=">=1.0,!=1.5.*" autocomplete="off">
      <input aria-label="Version (optional)" placeholder="Version (optional)" autocomplete="off">
      <button type="submit">Check</button>
      <output aria-live="polite"></output>
    </form>
