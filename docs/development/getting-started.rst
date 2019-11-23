Getting started
===============

Working on packaging requires the installation of a small number of
development dependencies. To see what dependencies are required to
run the tests manually, please look at the ``tox.ini`` file.

Running tests
~~~~~~~~~~~~~

The packaging unit tests are found in the ``tests/`` directory and are
designed to be run using `pytest`_. `pytest`_ will discover the tests
automatically, so all you have to do is:

.. code-block:: console

    $ python -m pytest
    ...
    62746 passed in 220.43 seconds

This runs the tests with the default Python interpreter. This also allows
you to run select tests instead of the entire test suite.

You can also verify that the tests pass on other supported Python interpreters.
For this we use `tox`_, which will automatically create a `virtualenv`_ for
each supported Python version and run the tests. For example:

.. code-block:: console

    $ tox
    ...
     py27: commands succeeded
    ERROR:   pypy: InterpreterNotFound: pypy
    ERROR:   py34: InterpreterNotFound: python3.4
    ERROR:   py35: InterpreterNotFound: python3.5
     py36: commands succeeded
    ERROR:   py37: InterpreterNotFound: python3.7
     docs: commands succeeded
     pep8: commands succeeded

You may not have all the required Python versions installed, in which case you
will see one or more ``InterpreterNotFound`` errors.

If you wish to run just the linting rules, you may use `pre-commit`_.


Building documentation
~~~~~~~~~~~~~~~~~~~~~~

packaging documentation is stored in the ``docs/`` directory. It is
written in `reStructured Text`_ and rendered using `Sphinx`_.

Use `tox`_ to build the documentation. For example:

.. code-block:: console

    $ tox -e docs
    ...
    docs: commands succeeded
    congratulations :)

The HTML documentation index can now be found at
``docs/_build/html/index.html``.

.. _`pytest`: https://pypi.org/project/pytest/
.. _`tox`: https://pypi.org/project/tox/
.. _`virtualenv`: https://pypi.org/project/virtualenv/
.. _`pip`: https://pypi.org/project/pip/
.. _`sphinx`: https://pypi.org/project/Sphinx/
.. _`reStructured Text`: http://sphinx-doc.org/rest.html
.. _`pre-commit`: https://pre-commit.com
