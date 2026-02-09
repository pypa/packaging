Release Process
===============

#. Checkout the current ``main`` branch.

#. Install the latest ``nox``::

    $ pip install nox

#. Manually update the changelog to list all unreleased changes. Also verify
   that no new changes were added to a previous release in an earlier PR due to
   merge/rebase issues.

#. Run the release automation with the required version number (YY.N)::

    $ nox -s release -- YY.N

   This creates a new tag for the release. It will tell you how to push the tag.

#. Push the tag (command will be printed out in the last step).

#. Run the 'Publish' manual GitHub workflow, specifying the Git tag's commit
   SHA. This will build and publish the package to PyPI. Publishing will wait
   for any `required approvals`_.

#. Once it is approved and published to PyPI, add a
   `release on GitHub <https://github.com/pypa/packaging/releases>`__.
   Changelog can be auto-generated, but compare with the official changelog
   too.

.. note::

   Access that is needed for making the release are:

   - PyPI maintainer (or owner) access to ``packaging``
   - push directly to the ``main`` branch on the source repository
   - push tags directly to the source repository

.. _required approvals: https://docs.github.com/en/actions/managing-workflow-runs-and-deployments/managing-deployments/reviewing-deployments#approving-or-rejecting-a-job
