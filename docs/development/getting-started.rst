Getting started
===============

Working on packaging requires the installation of a small number of
development dependencies. These are listed in ``dev-requirements.txt`` and they
can be installed in a `virtualenv`_ using `pip`_. Once you've installed the
dependencies, install packaging in ``editable`` mode. For example:

.. code-block:: console

    $ # Create a virtualenv and activate it
    $ python -m pip install --requirement dev-requirements.txt
    $ python -m pip install --editable .

You are now ready to run the tests and build the documentation.

Running tests
~~~~~~~~~~~~~

packaging unit tests are found in the ``tests/`` directory and are
designed to be run using `pytest`_. `pytest`_ will discover the tests
automatically, so all you have to do is:

.. code-block:: console

    $ python -m pytest
    ...
    62746 passed in 220.43 seconds

This runs the tests with the default Python interpreter.

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
