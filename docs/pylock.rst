Lock Files
==========

.. currentmodule:: packaging.pylock

Parse and validate `pylock.toml files <https://packaging.python.org/en/latest/specifications/pylock-toml/>`_.

Usage
-----

.. code-block:: python

    import tomllib
    from pathlib import Path

    from packaging.pylock import Package, PackageWheel, Pylock
    from packaging.utils import NormalizedName
    from packaging.version import Version

    # validate a pylock file name
    assert is_valid_pylock_path(Path("pylock.example.toml"))

    # parse and validate pylock file
    toml_dict = tomllib.loads(Path("pylock.toml").read_text(encoding="utf-8"))
    pylock = Pylock.from_dict(toml_dict)
    # the resulting pylock object is validated against the specification,
    # else a PylockValidationError is raised

    # generate a pylock file
    pylock = Pylock(
        lock_version=Version("1.0"),
        created_by="some_tool",
        packages=[
            Package(
                name=NormalizedName("example-package"),
                version=Version("1.0.0"),
                wheels=[
                    PackageWheel(
                        url="https://example.com/example_package-1.0.0-py3-none-any.whl",
                        hashes={"sha256": "0fd.."},
                    )
                ],
            )
        ],
    )
    toml_dict = pylock.to_dict()
    # use a third-party library to serialize to TOML

    # you can validate a manually constructed Pylock class
    pylock.validate()

Reference
---------

.. autofunction:: is_valid_pylock_path

The following frozen keyword-only dataclasses are used to represent the
structure of a pylock file. The attributes correspond to the fields in the
pylock file specification.

.. autoclass:: Pylock
    :members: from_dict, to_dict, validate
    :exclude-members: __init__, __new__

.. class:: Package

.. class:: PackageWheel

.. class:: PackageSdist

.. class:: PackageArchive

.. class:: PackageVcs

.. class:: PackageDirectory

The following exception may be raised by this module:

.. autoexception:: PylockValidationError
    :exclude-members: __init__, __new__

.. autoexception:: PylockUnsupportedVersionError
    :exclude-members: __init__, __new__
