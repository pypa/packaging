Specifiers
==========

A core requirement of dealing with dependencies is the ability to
specify what versions of a dependency are acceptable for you.

See `Version Specifiers Specification`_ for more details on the exact
format implemented in this module, for use in Python Packaging tooling.

.. _Version Specifiers Specification: https://packaging.python.org/en/latest/specifications/version-specifiers/

Usage
-----

.. doctest::

    >>> from packaging.specifiers import SpecifierSet
    >>> from packaging.version import Version
    >>> spec1 = SpecifierSet("~=1.0")
    >>> spec1
    SpecifierSet('~=1.0')
    >>> spec2 = SpecifierSet(">=1.0")
    >>> spec2
    SpecifierSet('>=1.0')
    >>> # We can combine specifiers
    >>> combined_spec = spec1 & spec2
    >>> combined_spec
    SpecifierSet('>=1.0,~=1.0')
    >>> # We can also implicitly combine a string specifier
    >>> combined_spec &= "!=1.1"
    >>> combined_spec
    SpecifierSet('!=1.1,>=1.0,~=1.0')
    >>> # We can iterate over the SpecifierSet to recover the
    >>> # individual specifiers
    >>> sorted(combined_spec, key=str)
    [Specifier('!=1.1'), Specifier('>=1.0'), Specifier('~=1.0')]
    >>> # Create a few versions to check for contains.
    >>> v1 = Version("1.0a5")
    >>> v2 = Version("1.0")
    >>> # We can check a version object to see if it falls within a specifier
    >>> v1 in combined_spec
    False
    >>> v2 in combined_spec
    True
    >>> # We can even do the same with a string based version
    >>> "1.4" in combined_spec
    True
    >>> # Finally we can filter a list of versions to get only those which are
    >>> # contained within our specifier.
    >>> list(combined_spec.filter([v1, v2, "1.4"]))
    [Version('1.0'), '1.4']


Reference
---------

.. automodule:: packaging.specifiers
    :members:
    :special-members:
