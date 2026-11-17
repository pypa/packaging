Getting started
===============

In an activated virtual environment, install Nox from the development lock:

.. code-block:: console

    $ uv pip install -r pylock.dev.toml
    $ nox -s tests

The test, documentation and lint sessions install their groups from this file.

For an environment with all development tools, use the ``dev`` group:

.. code-block:: console

    $ uv pip install -r pylock.dev.toml --group dev
    $ uv pip install --no-deps --no-build-isolation -e .

Pip 26.3 or newer can install the same selection with
``python -m pip install --group pylock.dev.toml:dev``. Nox retains its usual
environment backend. Select ``dev`` to combine the development tools.

Running tests
~~~~~~~~~~~~~

The packaging unit tests are found in the ``tests/`` directory and are
designed to be run using `pytest`_. `pytest`_ will discover the tests
automatically, so all you have to do is:

.. code-block:: console

    $ python -m pytest
    ...
    29204 passed, 4 skipped, 1 xfailed in 83.98 seconds

This runs the tests with the default Python interpreter. This also allows
you to run select tests instead of the entire test suite.

You can also verify that the tests pass on other supported Python interpreters.
For this we use `nox`_, which will automatically create a `virtualenv`_ for
each supported Python version and run the tests. For example:

.. code-block:: console

    $ nox -s tests
    ...
    nox > Ran multiple sessions:
    nox > * tests-3.10: success
    nox > * tests-3.11: success
    nox > * tests-3.12: success
    nox > * tests-3.13: success
    nox > * tests-3.14: success
    nox > * tests-3.15: success
    nox > * tests-3.13t: success
    nox > * tests-3.14t: success
    nox > * tests-3.15t: success
    nox > * tests-pypy3.10: skipped
    nox > * tests-pypy3.11: skipped

You may not have all the required Python versions installed, in which case you
will see one or more ``InterpreterNotFound`` errors.

Running property-based tests
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The tests under ``tests/property/`` use `Hypothesis`_ and are gated by the
``property`` pytest marker. They are excluded from the default ``pytest``
run (and from ``nox -s tests``) so that downstream packagers and CI stay
fast. To run them explicitly:

.. code-block:: console

    $ python -m pytest -m property

Or via `nox`_:

.. code-block:: console

    $ nox -s property_tests

Running linters
~~~~~~~~~~~~~~~

If you wish to run the linting rules, you may use `pre-commit`_ or run
``nox -s lint``.

.. code-block:: console

    $ nox -s lint
    ...
    nox > Session lint was successful.

Building documentation
~~~~~~~~~~~~~~~~~~~~~~

packaging documentation is stored in the ``docs/`` directory. It is
written in `reStructured Text`_ and rendered using `Sphinx`_.

Use `nox`_ to build the documentation. For example:

.. code-block:: console

    $ nox -s docs
    ...
    nox > Session docs was successful.

The HTML documentation index can now be found at
``docs/_build/html/index.html``.

Updating dependencies
~~~~~~~~~~~~~~~~~~~~~

Refresh the development and build locks with ``nox -s locks -- --upgrade``. Use
``nox -s locks -- --locked`` to check the committed files.

The pickle compatibility sessions install historical packaging releases from
separate files under ``tasks/pickle/``. The locks session refreshes these too.

Build and deployment tools use the separate
``pylock.build.toml``. Its requirements come from the ``build`` group and
``build-system.requires`` in ``pyproject.toml``; ``tool.nab.plans.build``
selects its single Python 3.14 Linux environment and requires wheels for every package.
Builds use the installed backend
without creating an additional build environment.

.. _`pytest`: https://pypi.org/project/pytest/
.. _`nox`: https://pypi.org/project/nox/
.. _`virtualenv`: https://pypi.org/project/virtualenv/
.. _`pip`: https://pypi.org/project/pip/
.. _`sphinx`: https://pypi.org/project/Sphinx/
.. _`reStructured Text`: https://www.sphinx-doc.org/en/master/usage/restructuredtext/
.. _`pre-commit`: https://pre-commit.com
.. _`Hypothesis`: https://pypi.org/project/hypothesis/
