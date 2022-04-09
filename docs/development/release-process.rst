.. SPDX-FileCopyrightText: 2014-2022 Donald Stufft and individual contributors. All rights reserved.
..
.. SPDX-License-Identifier: BSD-2-Clause OR Apache-2.0

Release Process
===============

#. Checkout the current ``main`` branch.
#. Install the latest ``nox``::

    $ pip install nox

#. Run the release automation with the required version number (YY.N)::

    $ nox -s release -- YY.N

   You will need the password for your GPG key as well as an API token for PyPI.

#. Add a `release on GitHub <https://github.com/pypa/packaging/releases>`__.

#. Notify the other project owners of the release.

.. note::

   Access needed for making the release are:

   - PyPI maintainer (or owner) access to ``packaging``
   - push directly to the ``main`` branch on the source repository
   - push tags directly to the source repository
