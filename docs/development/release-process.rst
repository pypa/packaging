Release Process
===============

#. Checkout the current ``main`` branch.
#. Install the latest ``nox``::

    $ pip install nox

#. Manually update the changelog to list all unreleased changes. Also verify that no new changes were added to a previous release in an earlier PR due to merge/rebase issues.
#. Run the release automation with the required version number (YY.N)::

    $ nox -s release -- YY.N

   This creates and pushes a new tag for the release

#. Add a `release on GitHub <https://github.com/pypa/packaging/releases>`__.

   This triggers a CI workflow which builds and publishes the package to PyPI

#. Notify the other project owners of the release.

.. note::

   Access needed for making the release are:

   - PyPI maintainer (or owner) access to ``packaging``
   - push directly to the ``main`` branch on the source repository
   - push tags directly to the source repository
