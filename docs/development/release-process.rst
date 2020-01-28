Release Process
===============

#. Checkout the current ``master`` branch.
#. Install the latest ``nox``::

    $ pip install nox

#. Modify the ``CHANGELOG.rst`` to include changes made since the last release
   and update the section header for the new release.

#. Run the release automation with the required version number (YY.N)::

    $ nox -s release -- YY.N

#. Modify the ``CHANGELOG.rst`` to reflect the development version does not
   have any changes since the last release.

#. Notify the other project owners of the release.

.. note::
   Access needed for making the release are:

   - PyPI maintainer (or owner) access to `packaging`
   - push directly to the `master` branch on the source repository
   - push tags directly to the source repository
