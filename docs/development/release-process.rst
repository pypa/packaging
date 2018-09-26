Release Process
===============

#. Checkout the current ``master`` branch, with a clean working directory.
#. Modify the ``CHANGELOG.rst`` to include changes made since the last release.
#. Bump the version in ``packaging/__about__.py``

#. Install the latest ``setuptools``, ``wheel`` and ``twine`` packages
   from PyPI::

    $ pip install --update setuptools wheel twine

#. Ensure no ``dist/`` folder exists and then create the distribution files::

    $ python setup.py sdist bdist_wheel

#. Check the built distribution files with ``twine``::

    $ twine check dist/*

#. If all goes well, upload the build distribution files::

    $ twine upload dist/*

#. Bump the version for development in ``packaging/__about__.py`` and
   ``CHANGELOG.rst``.
